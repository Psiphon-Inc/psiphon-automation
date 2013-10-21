#!/usr/bin/python
#
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
#


import collections
from collections import defaultdict
from collections import OrderedDict
import psycopg2
import psi_ops_stats_credentials
from mako.template import Template
from mako.lookup import TemplateLookup
from mako import exceptions
import pynliner
import os
import sys
import json

# Using the FeedbackDecryptor's mail capabilities
sys.path.append(os.path.abspath(os.path.join('..', 'EmailResponder')))
sys.path.append(os.path.abspath(os.path.join('..', 'EmailResponder', 'FeedbackDecryptor')))
import sender
from config import config


PSI_OPS_DB_FILENAME = os.path.join(os.path.abspath('.'), 'psi_ops_stats.dat')


def connections_on_hosts_in_interval(db_conn, interval):
    query = '''
        select host_id, count(host_id) from connected
        where timestamp between current_timestamp - interval '{0}' and current_timestamp - interval '{1}'
        group by host_id;
        '''
    cursor = db_conn.cursor()
    cursor.execute(query.format(interval[0], interval[1]))
    rows = cursor.fetchall()
    connections = {}
    for row in rows:
        connections[row[0]] = row[1]
    cursor.close()
    return connections


def render_mail(data):
    '''
    Will throw exception if data does not match expected structure (that is,
    if the template rendering fails).
    '''

    template_filename = 'psi_mail_host_stats.mako'
    template_lookup = TemplateLookup(directories=[os.path.dirname(os.path.abspath(__file__))])

    # SECURITY IMPORTANT: `'h'` in the `default_filters` list causes HTML
    # escaping to be applied to all expression tags (${...}) in this
    # template. Because we're output untrusted user-supplied data, this is
    # essential.
    template = Template(filename=template_filename,
                        default_filters=['unicode', 'h'],
                        lookup=template_lookup)

    try:
        rendered = template.render(data=data)
    except:
        raise Exception(exceptions.text_error_template().render())

    # CSS in email HTML must be inline
    rendered = pynliner.fromString(rendered)

    return rendered


column_specs = [
    ('Yesterday', '40 hours', '16 hours'),
    ('1 week ago', '208 hours', '184 hours'),
    ('Past Week', '184 hours', '16 hours'),
]


if __name__ == "__main__":

    with open(PSI_OPS_DB_FILENAME) as file:
        psinet = json.loads(file.read())

    Host = collections.namedtuple(
        'Host',
        'id, provider, datacenter, region')

    hosts = [Host(host['id'],
                  host['provider'],
                  host['datacenter_name'],
                  host['region'])
             for host in psinet['_PsiphonNetwork__hosts'].itervalues()]

    host_connections = {}
    provider_connections = {}
    datacenter_connections = {}
    region_connections = {}

    db_conn = psycopg2.connect(
        'dbname=%s user=%s password=%s host=%s port=%d' % (
            psi_ops_stats_credentials.POSTGRES_DBNAME,
            psi_ops_stats_credentials.POSTGRES_USER,
            psi_ops_stats_credentials.POSTGRES_PASSWORD,
            psi_ops_stats_credentials.POSTGRES_HOST,
            psi_ops_stats_credentials.POSTGRES_PORT))

    def set_connections(host, connections, column_name):
        if not host.id in host_connections:
            host_connections[host.id] = defaultdict(int)
        if not host.provider in provider_connections:
            provider_connections[host.provider] = defaultdict(int)
        if not host.datacenter in datacenter_connections:
            datacenter_connections[host.datacenter] = defaultdict(int)
        if not host.region in region_connections:
            region_connections[host.region] = defaultdict(int)
        host_connections[host.id][column_name] = connections
        provider_connections[host.provider][column_name] += connections
        datacenter_connections[host.datacenter][column_name] += connections
        region_connections[host.region][column_name] += connections

    for spec in column_specs:
        connections_for_spec = connections_on_hosts_in_interval(db_conn, (spec[1], spec[2]))
        for host in hosts:
            c = 0
            if host.id in connections_for_spec:
                c = connections_for_spec[host.id]
            set_connections(host, c, spec[0])

    def add_table(tables, title, key, connections):
        tables[title] = {}
        tables[title]['headers'] = [key] + [spec[0] for spec in column_specs]
        tables[title]['data'] = sorted(connections.items(), key=lambda x: x[1][column_specs[0][0]], reverse=True)

    tables_data = OrderedDict()
    add_table(tables_data, 'Connections to Regions', 'Region', region_connections)
    add_table(tables_data, 'Connections to Providers', 'Provider', provider_connections)
    add_table(tables_data, 'Connections to Datacenters', 'Datacenter', datacenter_connections)
    add_table(tables_data, 'Connections to Hosts', 'Host', host_connections)

    db_conn.close()

    html_body = render_mail(tables_data)

    sender.send(config['statsEmailRecipients'],
                config['emailUsername'],
                'Psiphon 3 Host Stats',
                repr(tables_data),
                html_body)

