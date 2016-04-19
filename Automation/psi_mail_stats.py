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


from collections import defaultdict
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


# Using the FeedbackDecryptor's mail capabilities
sys.path.append(os.path.abspath(os.path.join('..', 'EmailResponder')))
sys.path.append(os.path.abspath(os.path.join('..', 'EmailResponder', 'FeedbackDecryptor')))
# import sender
# from config import config

es = None

class ElasticsearchUnreachableException(Exception):
    def __init__(self, passedHost):
        self.passedHost = passedHost

    def __unicode__(self):
        return "The Elasticsearch cluster at '%s' is not reachable" % (self.passedHost)

    def __str__(self):
        return unicode(self).encode("utf-8")

# Main function to do the search based on query and time
def _get_connected(query_files, index_param):
    res = None

    startTime = time()
    print("[%s] Starting query - 30 minute timeout" % datetime.datetime.now())


    # "query.json" is JSON object in a file that is a valid elasticsearch query
    with open(query_files, 'r') as f:
        query = json.load(f)
        res = es.search(index=index_param, body=query, request_timeout=1800)
        print("[%s] Finished in %.2fs" % (datetime.datetime.now(), round((time()-startTime), 2)))
        return res['aggregations']


def render_mail(data):
    '''
    Will throw exception if data does not match expected structure (that is,
    if the template rendering fails).
    '''

    template_filename = 'psi_mail_stats.mako'
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


if __name__ == "__main__":

    tables_data = {}
    tables_data['table_columns'] = [
        ('Yesterday', '36 hours', '12 hours'),
        ('1 week ago', '204 hours', '180 hours'),
        ('Past Week', '180 hours', '12 hours'),
    ]

    try:
        es = Elasticsearch(hosts=['192.168.1.165:12251'], retry_on_timeout=True, max_retries=3)
        if not es.ping():
            raise ElasticsearchUnreachableException(elasticsearch)

        # index_param = "psiphon-connected-{:%Y.%m.%d}".format(today)
        # More eff way to query, only use 8 days index
        index_connections = "psiphon-connected-*"
        index_unique_users = "aggregated-connected-*"
        index_page_views = "psiphon-page_views-*"

        # Different query for Unique users and Connections
        connections_result = _get_connected('./Query/query_connections.json', index_connections)
        unique_users_result = _get_connected('./Query/query_unique_users.json', index_unique_users)

        tables_data['connections'] = connections_result
        tables_data['unique_users'] = unique_users_result

        # page_views_result = _get_connected('query_page_views.json', index_page_views)
        # print page_views_result

    except ElasticsearchUnreachableException as e:
        print("Could not initialize. The Elasticsearch cluster at '%s' is unavailable" % (e.passedHost))

    html_body = render_mail(tables_data)

    print(html_body)

    # sender.send(config['statsEmailRecipients'],
    #             config['emailUsername'],
    #             'Psiphon 3 Stats',
    #             repr(tables_data),
    #             html_body)
