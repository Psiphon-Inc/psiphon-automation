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

import psi_ssh

sys.path.insert(0, os.path.abspath(os.path.join('..', 'Data')))
import psi_db


#==== Log File Configuration  ==================================================

HOST_LOG_DIR = '/var/log'
HOST_LOG_FILENAME_PATTERN = 'psiphonv*.log*'

STATS_ROOT = os.path.abspath(os.path.join('..', 'Data', 'Stats'))
STATS_DB_FILENAME = os.path.join(STATS_ROOT, 'stats.db')

# if psi_build_config.py exists, load it and use psi_build_config.DATA_ROOT as the data root dir

if os.path.isfile('psi_data_config.py'):
    import psi_data_config
    psi_db.set_db_root(psi_data_config.DATA_ROOT)
    STATS_ROOT = os.path.join(psi_data_config.DATA_ROOT, 'Stats')
    STATS_DB_FILENAME = os.path.join(STATS_ROOT, 'stats.db')


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

LOG_LINE_PATTERN = '([\dT\.:-]+) (\w+) psiphonv: (\w+) (.+)'

LOG_ENTRY_COMMON_FIELDS = ('timestamp', 'host_id')

LOG_EVENT_TYPE_SCHEMA = {
    'started' :         ('server_id',),
    'handshake' :       ('server_id',
                         'client_region',
                         'client_id',
                         'sponsor_id',
                         'client_version'),
    'discovery' :       ('server_id',
                         'client_region',
                         'client_id',
                         'sponsor_id',
                         'client_version',
                         'discovery_server_id',
                         'client_unknown'),
    'connected' :       ('server_id',
                         'client_region',
                         'client_id',
                         'sponsor_id',
                         'client_version',
                         'client_vpn_ip_address'),
    'download' :        ('server_id',
                         'client_region',
                         'client_id',
                         'sponsor_id',
                         'client_version',
                         'client_vpn_ip_address'),
    'disconnected' :    ('client_vpn_ip_address',)}


def init_stats_db(db):

    # Create (if doesn't exist) a database table for each event type with
    # a column for every expected field. The primary key constaint includes all
    # table columns and transparently handles the uniqueness logic -- duplicate
    # log lines are discarded. SQLite automatically creates an index for this.

    for (event_type, event_fields) in LOG_EVENT_TYPE_SCHEMA.items():
        field_names = LOG_ENTRY_COMMON_FIELDS + event_fields
        command = textwrap.dedent('''
            create table if not exists %s
                (%s,
                constraint pk primary key (%s) on conflict ignore)''') % (
            event_type,
            ', '.join(['%s text' % (name,) for name in field_names]),
            ', '.join(field_names))
        db.execute(command)


def pull_stats(db, host):

    print 'pull stats from host %s...' % (host.Host_ID,)

    server_ip_address_to_id = {}
    for server in psi_db.get_servers():
        server_ip_address_to_id[server.IP_Address] = server.Server_ID

    line_re = re.compile(LOG_LINE_PATTERN)

    ssh = psi_ssh.SSH(
            host.IP_Address, host.SSH_Username,
            host.SSH_Password, host.SSH_Host_Key)

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
                            # SSL errors are common, so don't alert
                            if line.find('SSL') == -1:
                                err = 'unexpected log line pattern: %s' % (line,)
                                print err
                            continue
                        timestamp = match.group(1)
                        host_id = match.group(2)
                        event_type = match.group(3)
                        event_values = match.group(4).split()
                        event_fields = LOG_EVENT_TYPE_SCHEMA[event_type]
                        if len(event_values) != len(event_fields):
                            err = 'invalid log line fields %s' % (line,)
                            print err
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


if __name__ == "__main__":

    if not os.path.exists(STATS_ROOT):
        os.makedirs(STATS_ROOT)
    db = sqlite3.connect(STATS_DB_FILENAME)

    try:
        init_stats_db(db)

        # Pull stats from each host

        hosts = psi_db.get_hosts()
        for host in hosts:
            pull_stats(db, host)
    finally:
        db.close()
