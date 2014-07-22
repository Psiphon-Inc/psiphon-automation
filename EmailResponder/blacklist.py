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
import settings
from sqlalchemy import create_engine
from sqlalchemy import Column, String, Integer
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.exc import IntegrityError


_Base = declarative_base()


class _BlacklistAdhoc(_Base):
    __tablename__ = 'blacklist_adhoc'
    emailhash = Column(String(40), primary_key=True, nullable=False)
    count = Column(Integer, default=0, nullable=False)


class _BlacklistDomain(_Base):
    __tablename__ = 'blacklist_domain'
    domainhash = Column(String(40), primary_key=True, nullable=False)


class _BlacklistEmail(_Base):
    __tablename__ = 'blacklist_email'
    emailhash = Column(String(40), primary_key=True, nullable=False)


class _WhitelistDomain(_Base):
    __tablename__ = 'whitelist_domain'
    domainhash = Column(String(40), primary_key=True, nullable=False)


class _WhitelistEmail(_Base):
    __tablename__ = 'whitelist_email'
    emailhash = Column(String(40), primary_key=True, nullable=False)


_dbengine = create_engine('mysql://%s:%s@localhost/%s' % (settings.DB_USERNAME, settings.DB_PASSWORD, settings.DB_DBNAME))
_Base.metadata.create_all(_dbengine)
_Session = sessionmaker(bind=_dbengine)


class Blacklist(object):
    def __init__(self):
        pass

    def clear_adhoc(self):
        '''
        Deletes *all* entries from the blacklist table. Should be run exactly
        once a day (or whatever the blacklist window is).
        '''
        # Drop the table.
        _BlacklistAdhoc.__table__.drop(bind=_dbengine)

        # Re-create the table so that any immediately following calls won't fail.
        _BlacklistAdhoc.__table__.create(bind=_dbengine)

    def _hash_addr(self, email_addr):
        return hashlib.sha1(email_addr.lower()).hexdigest()

    def check_and_add(self, email_addr):
        '''
        Check if the given email address has exceeded the number of requests that
        it's allowed to make. Returns True if email_addr is allowed to get a
        reply, False otherwise.
        '''

        domain = email_addr[email_addr.rindex('@') + 1:]
        if not domain:
            return False

        # Is this address whitelisted via settings?
        if domain in settings.BLACKLIST_EXEMPTION_DOMAINS:
            return True

        # Is this domain blacklisted via settings?
        if domain in settings.BLACKLISTED_DOMAINS:
            return False

        emailhash = self._hash_addr(email_addr)

        dbsession = _Session()

        # Is this address whitelisted via DB info?
        if self.is_email_whitelisted(email_addr, dbsession) or \
           self.is_domain_whitelisted(domain, dbsession):
            return True

        # Is the user or his domain total blacklisted?
        if self.is_email_blacklisted(email_addr, dbsession) or \
           self.is_domain_blacklisted(domain, dbsession):
            return False

        match = dbsession.query(_BlacklistAdhoc).filter_by(emailhash=emailhash).first()

        if not match:
            newrecord = _BlacklistAdhoc(emailhash=emailhash, count=1)
            dbsession.add(newrecord)
        else:
            if match.count < settings.BLACKLIST_DAILY_LIMIT:
                match.count += 1
            else:
                # Request count limit exceeded
                return False

        # We added/incremented the request count for this user, but they haven't
        # exceeded the limit.

        try:
            dbsession.commit()
        except IntegrityError:
            # This can occur in a race condition scenario: two emails arrive
            # from the same email address at the same time; two
            # mail_process.py instances are created to process them; both
            # instances do  blacklist checks and don't find a pre-existing
            # entry; both  instances try to insert a new blacklist entry; the
            # last to commit get a duplicate primary key error.
            return False

        return True

    def add_to_blacklist(self, email_or_domain):
        '''
        Add a new email address or domain to the perma-blacklist.
        '''

        dbsession = _Session()

        hashvalue = self._hash_addr(email_or_domain)

        if '@' in email_or_domain:
            if self.is_email_blacklisted(email_or_domain, dbsession):
                print 'Email already blacklisted'
                return
            newrecord = _BlacklistEmail(emailhash=hashvalue)
            dbsession.add(newrecord)
        else:
            if self.is_domain_blacklisted(email_or_domain, dbsession):
                print 'Domain already blacklisted'
                return
            newrecord = _BlacklistDomain(domainhash=hashvalue)
            dbsession.add(newrecord)

        dbsession.commit()

    def is_domain_blacklisted(self, domain, dbsession=None):
        if not dbsession:
            dbsession = _Session()

        hashvalue = self._hash_addr(domain)
        match = dbsession.query(_BlacklistDomain).filter_by(domainhash=hashvalue).first()

        return match is not None

    def is_email_blacklisted(self, email_addr, dbsession=None):
        '''
        Check if the email address has been perma-blacklisted (doesn't check if
        it's in the "adhoc" blacklist).
        '''

        if not dbsession:
            dbsession = _Session()

        hashvalue = self._hash_addr(email_addr)
        match = dbsession.query(_BlacklistEmail).filter_by(emailhash=hashvalue).first()

        return match is not None

    def add_to_whitelist(self, email_or_domain):
        '''
        Add a new email address or domain to the perma-whitelist.
        '''

        dbsession = _Session()

        hashvalue = self._hash_addr(email_or_domain)

        if '@' in email_or_domain:
            if self.is_email_whitelisted(email_or_domain, dbsession):
                print 'Email already whitelisted'
                return
            newrecord = _WhitelistEmail(emailhash=hashvalue)
            dbsession.add(newrecord)
        else:
            if self.is_domain_whitelisted(email_or_domain, dbsession):
                print 'Domain already whitelisted'
                return
            newrecord = _WhitelistDomain(domainhash=hashvalue)
            dbsession.add(newrecord)

        dbsession.commit()

    def is_domain_whitelisted(self, domain, dbsession=None):
        if not dbsession:
            dbsession = _Session()

        hashvalue = self._hash_addr(domain)
        match = dbsession.query(_WhitelistDomain).filter_by(domainhash=hashvalue).first()

        return match is not None

    def is_email_whitelisted(self, email_addr, dbsession=None):
        '''
        Check if the email address has been perma-whitelisted (doesn't check if
        it's in the "adhoc" whitelist).
        '''

        if not dbsession:
            dbsession = _Session()

        hashvalue = self._hash_addr(email_addr)
        match = dbsession.query(_WhitelistEmail).filter_by(emailhash=hashvalue).first()

        return match is not None


if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Interact with the blacklist table')
    parser.add_argument('--clear-adhoc', action='store_true', help='clear all blacklist entries')
    parser.add_argument('--add-blacklist', action='store', help='add email or domain to blacklist')
    parser.add_argument('--add-whitelist', action='store', help='add email or domain to whitelist')
    args = parser.parse_args()

    if args.clear_adhoc:
        blacklist = Blacklist()
        blacklist.clear_adhoc()
    elif args.add_blacklist:
        blacklist = Blacklist()
        blacklist.add_to_blacklist(args.add_blacklist)
    elif args.add_whitelist:
        blacklist = Blacklist()
        blacklist.add_to_whitelist(args.add_whitelist)
    else:
        parser.error('no valid arg')
