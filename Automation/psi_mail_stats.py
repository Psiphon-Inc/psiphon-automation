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

# Using the FeedbackDecryptor's mail capabilities
import os
import sys
sys.path.append(os.path.abspath(os.path.join('..', 'EmailResponder')))
sys.path.append(os.path.abspath(os.path.join('..', 'EmailResponder', 'FeedbackDecryptor')))
os.chdir('../EmailResponder/FeedbackDecryptor')
import sender
from config import config


windows_connections_by_region_template =  '''
select client_region, count(*) as connections
from connected
where timestamp between current_timestamp - interval '{0}' and current_timestamp - interval '{1}'
and lower(client_platform) like 'windows%'
group by client_region
order by 2 desc
;'''


windows_connections_total_template = '''
select count(*) as total_connections
from connected
where timestamp between current_timestamp - interval '{0}' and current_timestamp - interval '{1}'
and lower(client_platform) like 'windows%'
;'''


android_connections_by_region_template =  '''
select client_region, count(*) as connections
from connected
where timestamp between current_timestamp - interval '{0}' and current_timestamp - interval '{1}'
and lower(client_platform) like 'android%'
group by client_region
order by 2 desc
;'''


android_connections_total_template = '''
select count(*) as total_connections
from connected
where timestamp between current_timestamp - interval '{0}' and current_timestamp - interval '{1}'
and lower(client_platform) like 'android%'
;'''


windows_unique_users_by_region_template = '''
select client_region, count(*) as uniques
from connected
where timestamp between current_timestamp - interval '{0}' and current_timestamp - interval '{1}'
and last_connected < current_timestamp - interval '{0}'
and lower(client_platform) like 'windows%'
group by client_region
order by 2 desc
;'''


windows_unique_users_total_template = '''
select count(*) as total_uniques
from connected
where timestamp between current_timestamp - interval '{0}' and current_timestamp - interval '{1}'
and last_connected < current_timestamp - interval '{0}'
and lower(client_platform) like 'windows%'
;'''


android_unique_users_by_region_template = '''
select client_region, count(*) as uniques
from connected
where timestamp between current_timestamp - interval '{0}' and current_timestamp - interval '{1}'
and last_connected < current_timestamp - interval '{0}'
and lower(client_platform) like 'android%'
group by client_region
order by 2 desc
;'''


android_unique_users_total_template = '''
select count(*) as total_uniques
from connected
where timestamp between current_timestamp - interval '{0}' and current_timestamp - interval '{1}'
and last_connected < current_timestamp - interval '{0}'
and lower(client_platform) like 'android%'
;'''


windows_page_views_by_region_template = '''
select client_region, sum(viewcount) as page_views
from page_views
where timestamp between current_timestamp - interval '{0}' and current_timestamp - interval '{1}'
and lower(client_platform) like 'windows%'
group by client_region
order by 2 desc
;'''


windows_page_views_total_template = '''
select sum(viewcount) as total_page_views
from page_views
where timestamp between current_timestamp - interval '{0}' and current_timestamp - interval '{1}'
and lower(client_platform) like 'windows%'
;'''


android_page_views_by_region_template = '''
select client_region, sum(viewcount) as page_views
from page_views
where timestamp between current_timestamp - interval '{0}' and current_timestamp - interval '{1}'
and lower(client_platform) like 'android%'
group by client_region
order by 2 desc
;'''


android_page_views_total_template = '''
select sum(viewcount) as total_page_views
from page_views
where timestamp between current_timestamp - interval '{0}' and current_timestamp - interval '{1}'
and lower(client_platform) like 'android%'
;'''


tables = [
(
    'Windows Connections',
     windows_connections_by_region_template,
     windows_connections_total_template
),
(
    'Android Connections',
     android_connections_by_region_template,
     android_connections_total_template
),
(
    'Windows Unique Users',
    windows_unique_users_by_region_template,
    windows_unique_users_total_template
),
(
    'Android Unique Users',
    android_unique_users_by_region_template,
    android_unique_users_total_template
),
(
    'Windows Page Views',
    windows_page_views_by_region_template,
    windows_page_views_total_template
),
(
    'Android Page Views',
    android_page_views_by_region_template,
    android_page_views_total_template
)
]


table_columns = [
('Yesterday', '40 hours', '16 hours'),
('1 week ago', '208 hours', '184 hours'),
('Past Week', '184 hours', '16 hours'),
]


if __name__ == "__main__":

    subject = 'Psiphon 3 Stats'

    body = '<pre>\n'

    db_conn = psycopg2.connect(
        'dbname=%s user=%s password=%s host=%s port=%d' % (
            psi_ops_stats_credentials.POSTGRES_DBNAME,
            psi_ops_stats_credentials.POSTGRES_USER,
            psi_ops_stats_credentials.POSTGRES_PASSWORD,
            psi_ops_stats_credentials.POSTGRES_HOST,
            psi_ops_stats_credentials.POSTGRES_PORT))

    for table in tables:
        body += '\n'
        body += table[0]
        body += '\n'
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
            cursor = db_conn.cursor()
            cursor.execute(table[2].format(column[1], column[2]))
            total = cursor.fetchone()[0]
            rows.append(('Total', total))
            cursor.close()
            for row in rows:
                region = str(row[0])
                if not region in table_dict:
                    table_dict[region] = defaultdict(int)
                table_dict[region][column[0]] = row[1]

        body += ''.join(['%12s' % (header,) for header in ['Region'] + columns])
        body += '\n'

        # Sorted by the last column, top 10 (+1 for the total row)
        for region, values in sorted(table_dict.items(), key=lambda x: x[1][columns[-1]], reverse=True)[:11]:
            row = []
            row.append(region)
            for column in columns:
                row.append("{:,}".format(values[column]))
            body += ''.join(['%12s' % (str(item),) for item in row])
            body += '\n'

    db_conn.close()

    body += '</pre>\n'

    sender.send(config['decryptedEmailRecipient'],
                config['emailUsername'],
                subject,
                body,
                body)

