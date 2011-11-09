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

'''
Intended to be run as a cron job to send SES quota and stats to desired email
address (using SES itself). Credentials for SES are expected to be in boto 
conf file or environment variables.

The MailStats class can be used to record stats about the mail responder.
'''

import json
import argparse
import MySQLdb as mdb
from boto.ses.connection import SESConnection
import settings
import sendmail



class MailStats(object):
    '''
    Writes new info to the database as requests come in (and are sucessful or not.)
    '''

    def __init__(self):
        self._conn = mdb.connect(user=settings.DB_ROOT_USERNAME, passwd=settings.DB_ROOT_PASSWORD)
        self._setup()
                
        self._conn = mdb.connect(user=settings.DB_DBNAME, passwd=settings.DB_PASSWORD, db=settings.DB_DBNAME)

    def _setup(self):
        cur = self._conn.cursor()
        
        # Note that the DB name doesn't seem to be parameterizable.
        
        # We're going to pre-check for the DB and the table even though we're 
        # using "IF NOT EXISTS", because otherwise it prints error text (which
        # causes a problem when it's a cron job).
        if not cur.execute('SHOW DATABASES') or (settings.DB_DBNAME,) not in cur.fetchall():
            cur.execute('CREATE DATABASE IF NOT EXISTS '+settings.DB_DBNAME)
            
        # The GRANT command implictly creates the user if it doesn't exist.
        cur.execute("GRANT ALL PRIVILEGES ON "+settings.DB_DBNAME+".* TO %s@'%%' IDENTIFIED BY %s WITH GRANT OPTION;", (settings.DB_USERNAME, settings.DB_PASSWORD,))
        
        cur.execute('USE '+settings.DB_DBNAME)
       
        if not cur.execute('SHOW TABLES IN '+settings.DB_DBNAME) or \
                not set((('stats_per_addr',), 
                         ('stats_exceptions',), 
                         ('stats_noreply',))).issubset(set(cur.fetchall())):
            cur.execute('CREATE TABLE IF NOT EXISTS stats_per_addr ( date DATE, addr VARCHAR(50) NOT NULL, count INT NOT NULL, PRIMARY KEY (date, addr) );')
            cur.execute('CREATE TABLE IF NOT EXISTS stats_exceptions ( date DATE PRIMARY KEY, count INT NOT NULL );')
            cur.execute('CREATE TABLE IF NOT EXISTS stats_noreply ( date DATE PRIMARY KEY, count INT NOT NULL );')
            cur.execute('CREATE TABLE IF NOT EXISTS stats_blacklist ( date DATE PRIMARY KEY, count INT NOT NULL );')
    
    def increment_stats_per_addr(self, addr):
        cur = self._conn.cursor()
        cur.execute('INSERT INTO stats_per_addr (date, addr, count) VALUES (CURRENT_DATE(), %s, 1) ON DUPLICATE KEY UPDATE count = count+1', (addr,))

    def increment_stats_exceptions(self):
        cur = self._conn.cursor()
        cur.execute('INSERT INTO stats_exceptions (date, count) VALUES (CURRENT_DATE(), 1) ON DUPLICATE KEY UPDATE count = count+1')

    def increment_stats_noreply(self):
        cur = self._conn.cursor()
        cur.execute('INSERT INTO stats_noreply (date, count) VALUES (CURRENT_DATE(), 1) ON DUPLICATE KEY UPDATE count = count+1')

    def increment_stats_blacklist(self):
        cur = self._conn.cursor()
        cur.execute('INSERT INTO stats_blacklist (date, count) VALUES (CURRENT_DATE(), 1) ON DUPLICATE KEY UPDATE count = count+1')


if __name__ == '__main__':

    # Open the connection. Uses creds from boto conf or env vars.
    conn = SESConnection()

    quota = conn.get_send_quota()
    
    # Getting an error when we try to call this. See:
    # http://code.google.com/p/boto/issues/detail?id=518
    #conn.close()
    
    email_body = ''
    email_body += json.dumps(quota, indent=2)
    email_body += '\n\n'

    subject = '[MailResponder] Stats'

    raw_email = sendmail.create_raw_email(settings.STATS_RECIPIENT_ADDRESS, 
                                          settings.STATS_SENDER_ADDRESS, 
                                          subject, 
                                          email_body)

    if not raw_email:
        exit(1)

    if not sendmail.send_raw_email_amazonses(raw_email, settings.STATS_SENDER_ADDRESS):
        exit(1)

    exit(0)

