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
import sqlite3
import traceback
import csv
import datetime
import calendar
import collections
import bisect
import base64
import hashlib
import socket
import time
if os.name == 'posix':
    import pexpect

import psi_ssh
import psi_ops


#==== Syslog File Configuration  ==============================================

HOST_LOG_DIR = '/var/log'
HOST_LOG_FILENAME_PATTERN = 'psiphonv*.log*'


#==== psi_ops DB Configuration  =================================================

PSI_OPS_ROOT = os.path.abspath(os.path.join('..', 'Data', 'PsiOps'))
PSI_OPS_DB_FILENAME = os.path.join(PSI_OPS_ROOT, 'psi_ops.dat')


#==== Stats DB Configuration  =================================================

STATS_ROOT = os.path.abspath(os.path.join('..', 'Stats'))
STATS_DB_FILENAME = os.path.join(STATS_ROOT, 'stats.db')


#==== Netflow Files Configuration  ============================================

HOST_NETFLOW_DIR = '/var/cache/nfdump'
NETFLOWS_ROOT = os.path.abspath(os.path.join('..', 'Data', 'Netflows'))


#==== DNS pcap File Configuration  ============================================

HOST_DNS_PCAPS_DIR = '/var/cache/dns-pcaps'
DNS_PCAPS_ROOT = os.path.abspath(os.path.join('..', 'Data', 'dns-pcaps'))


# if psi_build_config.py exists, load it and use psi_build_config.DATA_ROOT
# as the data root dir

if os.path.isfile('psi_data_config.py'):
    import psi_data_config
    PSI_OPS_ROOT = os.path.abspath(os.path.join(psi_data_config.DATA_ROOT, 'PsiOps'))
    PSI_OPS_DB_FILENAME = os.path.join(PSI_OPS_ROOT, 'psi_ops.dat')
    STATS_ROOT = os.path.join(psi_data_config.DATA_ROOT, '..', 'Stats')
    STATS_DB_FILENAME = os.path.join(STATS_ROOT, 'stats.db')
    NETFLOWS_ROOT = os.path.join(psi_data_config.DATA_ROOT, 'Netflows')
    DNS_PCAPS_ROOT = os.path.join(psi_data_config.DATA_ROOT, 'dns-pcaps')


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
# the same server from the same reion and client build.

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


def init_stats_db(db):

    # Create (if doesn't exist) a database table for each event type with
    # a column for every expected field. The primary key constraint includes all
    # table columns and transparently handles the uniqueness logic -- duplicate
    # log lines are discarded. SQLite automatically creates an index for this.

    for (event_type, event_fields) in LOG_EVENT_TYPE_SCHEMA.items() + ADDITIONAL_TABLES_SCHEMA.items():
        # (Note: won't work right if ADDITIONAL_TABLES_SCHEMA has key in LOG_EVENT_TYPE_SCHEMA)
        if LOG_EVENT_TYPE_SCHEMA.has_key(event_type):
            field_names = LOG_ENTRY_COMMON_FIELDS + event_fields
        else:
            field_names = event_fields
        command = textwrap.dedent('''
            create table if not exists %s
                (%s,
                constraint pk primary key (%s) on conflict ignore)''') % (
            event_type,
            ', '.join(['%s text' % (name,) for name in field_names]),
            ', '.join(field_names))
        db.execute(command)

    # "Upgrade" any records in the db that have timestamps specified in local time
    # to specify the timestamps in UTC

    for (event_type, event_fields) in LOG_EVENT_TYPE_SCHEMA.items():
        cursor = db.cursor()
        cursor.execute("select * from %s where timestamp not like '%%Z'" % (event_type,))
        for row in cursor:
            db.execute('update %s set timestamp = ? where timestamp = ?' % (event_type,),
                       [iso8601_to_utc(row[0]), row[0]])


def pull_stats(db, error_file, host, server_ip_address_to_id):

    print 'pull stats from host %s...' % (host.id,)

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
            print 'processing %s...' % (filename,)
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
                    command = 'insert into %s (%s) values (%s)' % (
                        event_type,
                        ', '.join(field_names),
                        ', '.join(['?']*len(field_values)))
                    db.execute(command, field_values)
            finally:
                # Always delete temporary downloaded log file
                if file:
                    file.close()
                os.remove(temp_file.name)
    ssh.close()


def reconstruct_sessions(db, start_date):
    # Populate the session table. For each connection, create a session. Some
    # connections will have no end time, depending on when the logs are pulled.
    # Find the end time by selecting the 'disconnected' event with the same
    # host_id and session_id soonest after the connected timestamp.

    # First, delete all sessions that we are about to reconstruct. This
    # is to avoid duplicate session entries in the case where a previous pull created
    # sessions with no end.
    db.execute("delete from session where session_start_timestamp > '%s'" % (start_date,))
    db.execute('vacuum')

    # TODO: there may be sessions that started before start_date that don't have an end
    # time.  We could iterate through each of those and try to find a new 'disconnected'
    # event for each, updating each when we find an end time.
    # This is not critical because sessions are used to map regions/sponsors/etc to
    # outbound stats, and that mapping handles sessions without end times.

    field_names = ADDITIONAL_TABLES_SCHEMA['session']
    cursor = db.cursor()
    cursor.execute("select * from connected where timestamp > '%s'" % (start_date,))
    for row in cursor:

        # Check for a corresponding disconnected event
        # Timestamp is string field, but ISO 8601 format has the
        # lexicographical order we want.
        # The timestamp string also includes a timezone, and the
        # lexicographical compare still works because we are only
        # comparing records from the same host (ie. same timezone).
        disconnected_row = db.execute(textwrap.dedent('''
                    select timestamp from disconnected
                    where timestamp > ?
                    and host_id = ?
                    and relay_protocol = ?
                    and session_id = ?
                    order by timestamp asc limit 1'''),
                    [row[0], row[1], row[7], row[8]]).fetchone()
        session_end_timestamp = disconnected_row[0] if disconnected_row else None

        command = 'insert into session (%s) values (%s)' % (
            ', '.join(field_names),
            ', '.join(['?']*len(field_names)))
        # Note: dependent on column orders in schema definitions
        connected_field_names = LOG_ENTRY_COMMON_FIELDS + LOG_EVENT_TYPE_SCHEMA['connected']
        assert(connected_field_names[0] == 'timestamp' and
               connected_field_names[1] == 'host_id' and
               connected_field_names[8] == 'session_id')
        db.execute(command, list(row[1:])+[row[0], session_end_timestamp])


# Get the RSA key fingerprint from the host's SSH_Host_Key
# Based on:
# http://stackoverflow.com/questions/6682815/deriving-an-ssh-fingerprint-from-a-public-key-in-python
def ssh_fingerprint(host_key):
    base64_key = base64.b64decode(host_key.split(' ')[1])
    md5_hash = hashlib.md5(base64_key).hexdigest()
    return ':'.join(a + b for a, b in zip(md5_hash[::2], md5_hash[1::2]))


def sync_directory(host, source_root, dest_root):

    print 'sync %s from host %s to local %s...' % (
                source_root, host.id, dest_root)

    dest_root_for_host = os.path.join(dest_root, host.id)
    if not os.path.exists(dest_root_for_host):
        os.makedirs(dest_root_for_host)
    
    # Log files on the host (source) are rotated, so we use the default rsync
    # configuration that does not delete files on the dest that are not
    # present on the source.

    rsync = pexpect.spawn('rsync -ae "ssh -p %s -l %s" %s:%s/ "%s"' %
                    (host.ssh_port, host.stats_ssh_username,
                     host.ip_address, source_root, dest_root_for_host))
    prompt = rsync.expect([ssh_fingerprint(host.ssh_host_key), 'password:'])
    if prompt == 0:
        rsync.sendline('yes')
        rsync.expect('password:')
        rsync.sendline(host.stats_ssh_password)
    else:
        rsync.sendline(host.stats_ssh_password)

    rsync.wait()

    return dest_root_for_host


def pull_dns_pcaps(host):

    print 'pull DNS pcaps from host %s...' % (host.id,)

    return sync_directory(host, HOST_DNS_PCAPS_DIR, DNS_PCAPS_ROOT)


class DomainLookup(object):

    # Use DNS pcap data to map IP addresess to domains. This is used to map
    # netflow destination addresses to domains.
    #
    # We found reverse DNS lookups to be inadequate for this purpose:
    # too slow, too many failed lookups, IPs used to host many
    # domains, reverse lookups loses context (e.g. youtube.com --> IP -->
    # [random prefix].google.com)
    #
    # So instead we record all actual DNS requests and responses and use
    # this to build a more accurate database.
    # The recording is performed on each host using tcpdump:
    #
    # tcpdump -w 'dnspcap_%Y%m%d-%H%M%S.pcap' -G 360 -z gzip -n -i eth0 port 53
    #
    # The set of pcap files is downloaded to the stats host which builds
    # the DomainLookup index.
    # There is no PII in the captured DNS data. Futhermore, the pcaps don't
    # map to netflows or SSH sessions, so we use include the DNS traffic
    # timestamps in our index and assume that for each netflow, the domain
    # corresponding to the destination IP address is the most recent DNS
    # response before the flow stat (not always the case, but a reasonable
    # approximation).

    Entry = collections.namedtuple('Entry', 'timestamp, domain')

    def __init__(self, dns_pcaps_root, start_date):

        # Build domain lookup index. Run each raw data file through tcpdump to
        # parse protocol. Example output lines:
        # REQUEST:  1314288801.731017 IP 1.2.3.4.64338 > 8.8.4.4.53: 55087+ A? m.twitter.com. (31)
        # RESPONSE: 1314288801.744304 IP 8.8.4.4.53 > 1.2.3.4.64338: 55087 3/0/0 CNAME mobile.twitter.com., A 199.59.149.240, A 199.59.148.96 (84)
        # Multiple requests and responses are interleaved in the output, so we
        # need to match them up using the IDs e.g., (55087+, 55087)
        
        TIMESTAMP_FIELD = 0
        ID_FIELD = 5
        DOMAIN_FIELD = 7
        DNS_RECORD_TYPE_FIELD = 6
        FIRST_RECORD_FIELD = 7

        self.index = collections.defaultdict(list)
        pending_requests = {}
        for item in os.listdir(dns_pcaps_root):
            path = os.path.join(dns_pcaps_root, item)
            if os.path.isfile(path):
                # Skip this file if it was created before start_date
                # Note the filename format specified above
                if start_date > item[8:16]:
                    continue
                if path.endswith('.gz'):
                    proc = os.popen('gunzip -c "%s" | /usr/sbin/tcpdump -n -r - -tt' % (path,), 'r')
                else:
                    proc = os.popen('/usr/sbin/tcpdump -n -r "%s" -tt' % (path,), 'r')                    
                while True:
                    line = proc.readline()
                    if not line:
                        break
                    fields = line.split(' ')
                    timestamp = fields[TIMESTAMP_FIELD]
                    id = fields[ID_FIELD]
                    if id[-1] == '+' and fields[DNS_RECORD_TYPE_FIELD] == 'A?':
                        domain = fields[DOMAIN_FIELD].rstrip('.')
                        pending_requests[id[:-1]] = domain
                    else:
                        domain = pending_requests.get(id)
                        # Note: domain could be None if DNS capture starts
                        # in the middle of a request
                        if domain:
                            for i in range(FIRST_RECORD_FIELD+1, len(fields), 2):
                                dns_record_type = fields[i-1]
                                if dns_record_type == 'A':
                                    # Sanity check: should be valid IP address
                                    ip_address = fields[i].rstrip(',')
                                    socket.inet_aton(ip_address)
                                    # Note: truncating decimal precision for reasons
                                    # explained in process_vpn_outbound_stats
                                    self.index[ip_address].append(
                                        DomainLookup.Entry(int(timestamp[:timestamp.find('.')]), domain))
                            del pending_requests[id]
        # Ensure entries for each IP address are sorted by response timestamp
        # Also remove duplicates
        for entries in self.index.itervalues():
            entries = list(set(entries))
            entries.sort(key=lambda x:x.timestamp)


    def get_domain(self, ip_address, request_timestamp):
        entries = self.index[ip_address]
        if not entries:
            return ip_address
        # Find the most recent entry before the request timestamp
        # If the flow start is before the first entry, still return the first entry
        domain = entries[0].domain
        for value in entries:
            if value.timestamp > request_timestamp:
                break
            domain = value.domain
        return domain


def pull_netflows(host, start_date):

    print 'pull netflows from host %s...' % (host.id,)

    dest_root_for_host = sync_directory(host, HOST_NETFLOW_DIR, NETFLOWS_ROOT)

    output_csv_path = dest_root_for_host + '.csv'
    os.system('TZ=GMT nfdump -q -t %s -R "%s" -o csv > "%s"' % (start_date, dest_root_for_host, output_csv_path))
    return output_csv_path


class SessionIndex(object):

    def __init__(self, db, host_id, start_date):

        SessionInfo = collections.namedtuple(
            'SessionInfo',
            'host_id, server_id, client_region, propagation_channel_id, sponsor_id, '+
            'client_version, relay_protocol, session_id, '+
            'session_start_timestamp, session_end_timestamp')

        class SortedArrayIndex:
            def __init__(self):
                self.keys = []
                self.data = []

        self.session_end_index = collections.defaultdict(SortedArrayIndex)
        self.session_start_index = collections.defaultdict(SortedArrayIndex)

        for sort_field, output_index in [
            ('session_end_timestamp', self.session_end_index),
            ('session_start_timestamp', self.session_start_index)]:

            cursor = db.execute(
                textwrap.dedent(
                '''select
                   host_id, server_id, client_region, propagation_channel_id, sponsor_id,
                   client_version, relay_protocol, session_id,
                   substr(session_start_timestamp,1,19), substr(session_end_timestamp,1,19)
                   from session
                   where host_id = ? and relay_protocol == 'VPN'
                   and (session_end_timestamp > ? or session_end_timestamp is null)
                   order by substr(%s,1,19) asc''' % sort_field),
                [host_id, start_date])

            for row in cursor:
                session_info = SessionInfo(*(list(row[:-2]) +
                                [calendar.timegm(datetime.datetime.strptime(row[-2], '%Y-%m-%dT%H:%M:%S').utctimetuple()),
                                 calendar.timegm(datetime.datetime.strptime(row[-1], '%Y-%m-%dT%H:%M:%S').utctimetuple()) if row[-1]
                                 else row[-1]]))
                sorted_array_index = output_index[session_info.session_id]
                sorted_array_index.keys.append(getattr(session_info,sort_field))
                sorted_array_index.data.append(session_info)

    def find_session_ending_on_or_after(self, session_id, flow_end_timestamp):

        # bisect usage from:
        # http://docs.python.org/library/bisect.html#searching-sorted-lists
        # http://docs.python.org/library/bisect.html#other-examples

        def find_ge(a, x):
            'Find leftmost item greater than or equal to x'
            array_index = bisect.bisect_left(a, x)
            if array_index != len(a):
                return array_index
            return None

        sessions = self.session_end_index.get(session_id)
        if not sessions:
            return None
        array_index = find_ge(sessions.keys, flow_end_timestamp)
        return sessions.data[array_index] if array_index else None

    def find_latest_started_session(self, session_id):
        sessions = self.session_start_index.get(session_id)
        if not sessions:
            return None
        return sessions.data[-1]


def process_vpn_outbound_stats(db, error_file, host_id, dns, csv_file, start_date):

    print 'processing vpn outbound stats from host %s...' % (host_id,)

    # Create an in-memory index for fast lookup of session start/end used
    # to map flows to sessions (to get region, prop channel etc. attributes)
    session_index = SessionIndex(db, host_id, start_date)

    db.execute("delete from outbound where relay_protocol = 'VPN' and host_id = '%s' and day >= '%s'" %
               (host_id, start_date))
    db.execute('vacuum')

    def to_unix_timestamp(timestamp):
        return calendar.timegm(datetime.datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S').utctimetuple())

    # CSV format
    #
    # HEADER:
    # ts,te,td,sa,da,
    # sp,dp,pr,flg,fwd,stos,ipkt,ibyt,opkt,obyt,in,out,
    # sas,das,smk,dmk,dtos,dir,nh,nhb,svln,dvln,ismc,odmc,idmc,osmc,
    # mpls1,mpls2,mpls3,mpls4,mpls5,mpls6,mpls7,mpls8,mpls9,mpls10,ra,eng
    #
    # SAMPLE ROW:
    # 2011-07-04 16:09:14,2011-07-04 16:09:14,0.351,10.1.0.2,208.69.58.58,
    # 4046,80,TCP,.AP.SF,0,0,6,686,0,0,117,100,
    # 0,0,0,0,0,0,0.0.0.0,0.0.0.0,0,0,00:00:00:00:00:00,00:00:00:00:00:00,00:00:00:00:00:00,00:00:00:00:00:00,
    # 0-0-0,0-0-0,0-0-0,0-0-0,0-0-0,0-0-0,0-0-0,0-0-0,0-0-0,0-0-0,0.0.0.0,0/0
    #
    # Note that there is no timezone info given in ts and te.  These timestamps
    # are reported in UTC.
    #
    # To compare netflow timestamps (which don't have millisecond resolution)
    # to session and dns timestamps, we truncate the session and dns timestamps
    # milliseconds and timezone info.
    # There is a small chance that multiple sessions will occur on the same
    # session_id (client vpn ip address) in the same second so that a flow
    # occuring in a single second will match both sessions.
    # TODO: investigate nf_dump -o extended millisecond resolution

    # In-memory counters to avoid millions of database writes
    outbound_rows = {}

    outbound_reader = csv.reader(csv_file)
    for row in outbound_reader:

        # Stop reading at the Summary row
        if 'Summary' in row:
            break

        # Skip blank rows
        if not len(row):
            continue

        # Skip flows before start_date
        if start_date > row[0]:
            continue

        # First find the earliest session that ends after the netflow end timestamp.
        session = session_index.find_session_ending_on_or_after(row[3], to_unix_timestamp(row[1]))

        if not session:
            # If we couldn't find a session end timestamp on or after the netflow end timestamp,
            # then the netflow must belong to the latest (or currently active) session.
            session = session_index.find_latest_started_session(row[3])

        # See CSV format above
        domain = dns.get_domain(row[4], to_unix_timestamp(row[0]))

        if not session:
            err = 'no session for outbound netflow on host %s: %s' % (host_id, str(row))
            error_file.write(err + '\n')
            field_values = [host_id, '0', '0', '0', '0', '0', 'VPN', row[3], 
                            row[0][0:10], domain, row[7], row[6], '1', str(int(row[12]) + int(row[14]))]
        else:
            field_values = list(session)[0:-2] + [
                            row[0][0:10], domain, row[7], row[6], '1', str(int(row[12]) + int(row[14]))]

        key = ','.join(field_values[0:-2])
        existing_row = outbound_rows.get(key)
        if existing_row:
            existing_row[-2] = str(int(existing_row[-2]) + int(field_values[-2])) # flow_count
            existing_row[-1] = str(int(existing_row[-1]) + int(field_values[-1])) # outbound_byte_count
        else:
            outbound_rows[key] = field_values

    field_names = ADDITIONAL_TABLES_SCHEMA['outbound']
    command = 'insert into outbound (%s) values (%s)' % (
              ', '.join(field_names),
              ', '.join(['?']*len(field_names)))
    db.executemany(command, outbound_rows.itervalues())


if __name__ == "__main__":

    psinet = psi_ops.PsiphonNetwork.load_from_file(PSI_OPS_DB_FILENAME)

    if not os.path.exists(STATS_ROOT):
        os.makedirs(STATS_ROOT)
    db = sqlite3.connect(STATS_DB_FILENAME)

    # Note: truncating error file
    error_file = open('pull_stats.err', 'w')

    # start_date is the date that we want to start processing session and netflow
    # data.  It is too time and memory consuming to attempt to process all
    # historical session and netflow data at once.  Processed statistics before
    # start_date will not be thrown out.
    # dns_start_date is before start date because we want to consider dns requests
    # that may have been cached by the client for a while.
    start_date = (datetime.datetime.utcnow() - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
    netflows_start_date = datetime.datetime.strptime(start_date, '%Y-%m-%d').strftime('%Y/%m/%d')
    dns_start_date = (datetime.datetime.strptime(start_date, '%Y-%m-%d') - datetime.timedelta(days=1)).strftime('%Y%m%d')

    try:
        init_stats_db(db)
        hosts = psinet.get_hosts()
        server_ip_address_to_id = {}
        for server in psinet.get_servers():
            server_ip_address_to_id[server.ip_address] = server.id

        # Pull stats from each host

        for host in hosts:
            pull_stats(db, error_file, host, server_ip_address_to_id)

        # Pull netflows from each host and process them
        # Avoid doing this on Windows, where nfdump is not available
        if os.name == 'posix':
            # Compute sessions from connected/disconnected records
    
            reconstruct_sessions(db, start_date)

            for host in hosts:

                csv_file_path = pull_netflows(host, netflows_start_date)

                # Construct domain lookup with data for current host only
                dns = DomainLookup(pull_dns_pcaps(host), dns_start_date)

                with open(csv_file_path, 'rb') as vpn_outbound_stats_csv:
                    process_vpn_outbound_stats(
                        db, error_file, host.id, dns, vpn_outbound_stats_csv, start_date)

                os.remove(csv_file_path)

    except socket.error:
        # If the DomainLookup throws this error, we need to notice it.
        db.execute("delete from outbound where day >= '%s'" % (start_date,))
    except:
        traceback.print_exc()
    finally:
        error_file.close()
        db.commit()
        db.close()
