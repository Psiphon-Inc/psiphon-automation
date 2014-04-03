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
import psycopg2
import psi_ops_stats_credentials

from mako.template import Template
from mako.lookup import TemplateLookup
from mako import exceptions
import pynliner

import os
import sys

# Using the FeedbackDecryptor's mail capabilities
sys.path.append(os.path.abspath(os.path.join('..', 'EmailResponder')))
sys.path.append(os.path.abspath(os.path.join('..', 'EmailResponder', 'FeedbackDecryptor')))
import sender
from config import config


windows_connections_by_region_template = '''
select client_region, count(*) as connections
from connected
where timestamp between current_timestamp - interval '{0}' and current_timestamp - interval '{1}'
and lower(client_platform) like 'windows%'
group by client_region
order by 2 desc
;'''


android_connections_by_region_template = '''
select client_region, count(*) as connections
from connected
where timestamp between current_timestamp - interval '{0}' and current_timestamp - interval '{1}'
and lower(client_platform) like 'android%'
group by client_region
order by 2 desc
;'''


windows_unique_users_by_region_template = '''
select client_region, count(*) as uniques
from connected
where timestamp between
  date_trunc('hour', current_timestamp) - interval '{0}' and
  date_trunc('hour', current_timestamp) - interval '{1}'
and last_connected < date_trunc('hour', current_timestamp) - interval '{0}'
and lower(client_platform) like 'windows%'
group by client_region
order by 2 desc
;'''


android_unique_users_by_region_template = '''
select client_region, count(*) as uniques
from connected
where timestamp between
 date_trunc('hour', current_timestamp) - interval '{0}' and
 date_trunc('hour', current_timestamp) - interval '{1}'
and last_connected < date_trunc('hour', current_timestamp) - interval '{0}'
and lower(client_platform) like 'android%'
group by client_region
order by 2 desc
;'''


windows_page_views_by_region_template = '''
select client_region, sum(viewcount) as page_views
from page_views
where timestamp between current_timestamp - interval '{0}' and current_timestamp - interval '{1}'
and lower(client_platform) like 'windows%'
group by client_region
order by 2 desc
;'''


android_page_views_by_region_template = '''
select client_region, sum(viewcount) as page_views
from page_views
where timestamp between current_timestamp - interval '{0}' and current_timestamp - interval '{1}'
and lower(client_platform) like 'android%'
group by client_region
order by 2 desc
;'''


tables = [
    (
        'Windows Connections',
        windows_connections_by_region_template,
    ),
    (
        'Android Connections',
        android_connections_by_region_template,
    ),
    (
        'Windows Unique Users',
        windows_unique_users_by_region_template,
    ),
    (
        'Android Unique Users',
        android_unique_users_by_region_template,
    ),
    (
        'Windows Page Views',
        windows_page_views_by_region_template,
    ),
    (
        'Android Page Views',
        android_page_views_by_region_template,
    )
]


table_columns = [
    ('Yesterday', '36 hours', '12 hours'),
    ('1 week ago', '204 hours', '180 hours'),
    ('Past Week', '180 hours', '12 hours'),
]


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

    db_conn = psycopg2.connect(
        'dbname=%s user=%s password=%s host=%s port=%d' % (
            psi_ops_stats_credentials.POSTGRES_DBNAME,
            psi_ops_stats_credentials.POSTGRES_USER,
            psi_ops_stats_credentials.POSTGRES_PASSWORD,
            psi_ops_stats_credentials.POSTGRES_HOST,
            psi_ops_stats_credentials.POSTGRES_PORT))

    tables_data = {}

    for table in tables:

        tables_data[table[0]] = {}

        table_dict = {}
        columns = []
        for column in table_columns:
            columns.append(column[0])
            # Regions
            cursor = db_conn.cursor()
            cursor.execute(table[1].format(column[1], column[2]))
            rows = cursor.fetchall()
            cursor.close()
            # Total
            total = 0
            for row in rows:
                total += row[1]
            rows.append(('Total', total))
            for row in rows:
                region = str(row[0])
                if not region in table_dict:
                    table_dict[region] = defaultdict(int)
                table_dict[region][column[0]] = row[1]

        tables_data[table[0]]['headers'] = ['Region'] + columns

        # Sorted by the last column, top 10 (+1 for the total row)
        tables_data[table[0]]['data'] = sorted(table_dict.items(), key=lambda x: x[1][columns[-1]], reverse=True)[:11]

    db_conn.close()

    html_body = render_mail(tables_data)

    sender.send(config['statsEmailRecipients'],
                config['emailUsername'],
                'Psiphon 3 Stats',
                repr(tables_data),
                html_body)
