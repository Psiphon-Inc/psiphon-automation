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
# import psycopg2
# import psi_ops_stats_credentials
from mako.template import Template
from mako.lookup import TemplateLookup
from mako import exceptions
import pynliner
import os
import sys
import json

import datetime
from time import time, mktime
from elasticsearch import ConflictError, NotFoundError, ConnectionTimeout, Elasticsearch, helpers as esHelpers

# Using the elasticsearch server enrty from a file
sys.path.append(os.path.abspath(os.path.join('.', 'Query')))
import psi_es_server_config as server_config

# Using the FeedbackDecryptor's mail capabilities
sys.path.append(os.path.abspath(os.path.join('..', 'EmailResponder')))
sys.path.append(os.path.abspath(os.path.join('..', 'EmailResponder', 'FeedbackDecryptor')))
import sender
from config import config

es = None
PSI_OPS_DB_FILENAME = os.path.join(os.path.abspath('.'), 'psi_ops_stats.dat')

class ElasticsearchUnreachableException(Exception):
    def __init__(self, passedHost):
        self.passedHost = passedHost

    def __unicode__(self):
        return "The Elasticsearch cluster at '%s' is not reachable" % (self.passedHost)

    def __str__(self):
        return unicode(self).encode("utf-8")

def _get_connected(interval, index_param):
    res = None

    query_files = './Query/hosts_stats.json'

    startTime = time()
    print("[%s] Starting query - 30 minute timeout" % datetime.datetime.now())


    # "query.json" is JSON object in a file that is a valid elasticsearch query
    with open(query_files, 'r') as f:
        query = json.load(f)

        query['query']['filtered']['filter']['bool']['must'][0]['range']['@timestamp']['gte'] = interval[0]
        query['query']['filtered']['filter']['bool']['must'][0]['range']['@timestamp']['lte'] = interval[1]

        res = es.search(index=index_param, body=query, request_timeout=1800)
        print("[%s] Finished in %.2fs" % (datetime.datetime.now(), round((time()-startTime), 2)))
        return res['aggregations']['2']['buckets']


def connections_on_hosts_in_interval(interval):
	# Different query for Unique users and Connections
    connections_result = _get_connected(interval, "psiphon-connected-*")
    connections = {}

    for entry in connections_result:
        connections[entry['key']] = entry['doc_count']

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
    ('Yesterday', 'now/d-24h', 'now/d'),
    ('1 week ago', 'now/d-192h', 'now/d-168h'),
    ('Past Week', 'now/d-168h', 'now/d'),
]

query_example = {}


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

    server_entry = server_config.ELASTICSEARCH_SERVER_IP_ADDRESS + ':' + server_config.ELASTICSEARCH_SERVER_PORT

    try:
    	es = Elasticsearch(hosts=[server_entry], retry_on_timeout=True, max_retries=3)
    	if not es.ping():
    			raise ElasticsearchUnreachableException(elasticsearch)

    except ElasticsearchUnreachableException as e:
        print("Could not initialize. The Elasticsearch cluster at '%s' is unavailable" % (e.passedHost))

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
        connections_for_spec = connections_on_hosts_in_interval((spec[1], spec[2]))
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

    html_body = render_mail(tables_data)


    sender.send(config['statsEmailRecipients'],
                config['emailUsername'],
                'Psiphon 3 Host Stats',
                repr(tables_data),
                html_body)
