#!/usr/bin/python
# -*- coding: utf-8 -*-

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
We want to limit the number of responses that we send to a single email address
in a day. This is both to hinder/prevent abuse of the system.
'''

import argparse
import hashlib
import MySQLdb as mdb
import settings



class Blacklist(object):
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
        cur.execute('SHOW DATABASES')
        if not cur.rowcount or (settings.DB_DBNAME,) not in cur.fetchall():
            cur.execute('CREATE DATABASE IF NOT EXISTS '+settings.DB_DBNAME)

        # The GRANT command implictly creates the user if it doesn't exist.
        cur.execute("GRANT ALL PRIVILEGES ON "+settings.DB_DBNAME+".* TO %s@'%%' IDENTIFIED BY %s WITH GRANT OPTION;", (settings.DB_USERNAME, settings.DB_PASSWORD,))
        
        cur.execute('USE '+settings.DB_DBNAME)
        
        cur.execute('SHOW TABLES IN '+settings.DB_DBNAME)
        if not cur.rowcount or ('blacklist',) not in cur.fetchall():
            cur.execute('CREATE TABLE IF NOT EXISTS blacklist ( emailhash CHAR(40) PRIMARY KEY, count TINYINT NOT NULL DEFAULT 0 );')
        
    def clear(self):
        '''
        Deletes *all* entries from the blacklist table. Should be run exactly 
        once a day (or whatever the blacklist window is).
        '''
        cur = self._conn.cursor()
        cur.execute('DELETE FROM blacklist')
        
    def _hash_addr(self, email_addr):
        return hashlib.sha1(email_addr.lower()).hexdigest()
        
    def check_and_add(self, email_addr):
        '''
        Check if the given email address has exceeded the number of requests that
        it's allowed to make. Returns True if email_addr is allowed to get a 
        reply, False otherwise.
        '''
        
        cur = self._conn.cursor()
        
        email_hash = self._hash_addr(email_addr)
        count = 0
        cur.execute('SELECT count FROM blacklist WHERE emailhash = %s', (email_hash,))
        if cur.rowcount > 0:
            count = cur.fetchall()[0][0]
            
        if count < settings.BLACKLIST_DAILY_LIMIT:
            cur.execute('INSERT INTO blacklist (emailhash, count) VALUES (%s, 1) ON DUPLICATE KEY UPDATE count = count+1', (email_hash,))
            return True
        
        return False

        
if __name__ == '__main__':
    
    parser = argparse.ArgumentParser(description='Interact with the blacklist table')
    parser.add_argument('--clear', action='store_true', help='clear all blacklist entries') 
    args = parser.parse_args()
    
    if args.clear:
        blacklist = Blacklist()
        blacklist.clear()
    else:
        parser.error('no valid arg')
        
        