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


import sys
import os
import syslog
import email
import email.header
import json
import re
import traceback
import time
import tempfile
import hashlib
from boto.s3.connection import S3Connection
from boto.s3.key import Key
from boto.exception import S3ResponseError

import settings
import sendmail
import blacklist



class MailResponder:
    '''
    Takes a configuration file and an email and sends back the appropriate 
    response to the sender.
    '''

    def __init__(self):
        self.requested_addr = None
        self._conf = None
        self._email = None

    def read_conf(self, conf_filepath):
        '''
        Reads in the given configuration file.
        Return True if successful, False otherwise.
        '''

        try:
            conffile = open(conf_filepath, 'r')

            self._response_from_addr = settings.RESPONSE_FROM_ADDR

            # Note that json.load reads in unicode strings
            self._conf = json.load(conffile)
            
            # Do some validation
            for key in self._conf.keys():
                item = self._conf[key]
                if not item.has_key('body') or not item.has_key('attachment_bucket'):
                    raise Exception('invalid config item: %s:%s', (key, repr(item)))
            
        except Exception as e:
            syslog.syslog(syslog.LOG_CRIT, 'error: config file read failed: %s' % e)
            return False

        return True

    def process_email(self, email_string):
        '''
        Processes the given email and sends a response.
        Returns True if successful, False or exception otherwise.
        '''

        if not self._parse_email(email_string):
            return False
        
        # Is this a verification email from Amazon SES?
        if self._check_verification_email():
            return False

        # Look up requested email address. 
        if not self._conf.has_key(self.requested_addr):
            syslog.syslog(syslog.LOG_INFO, 'fail: invalid requested address: %s' % self.requested_addr)
            return False
        
        # Check if the user is (or should be) blacklisted
        if not self._check_blacklist():
            syslog.syslog(syslog.LOG_INFO, 'fail: blacklist')
            return False
        
        attachment = None
        if self._conf[self.requested_addr]['attachment_bucket']:
            attachment = (get_s3_attachment(self._conf[self.requested_addr]['attachment_bucket']),
                          settings.ATTACHMENT_NAME)

        raw_response = sendmail.create_raw_email(self._requester_addr, 
                                                 self._response_from_addr,
                                                 self._subject,
                                                 self._conf[self.requested_addr]['body'],
                                                 attachment)

        if not raw_response:
            return False

        if not sendmail.send_raw_email_amazonses(raw_response, 
                                                 self._response_from_addr):
            return False

        return True

    def _check_blacklist(self):
        bl = blacklist.Blacklist()
        return bl.check_and_add(strip_email(self._requester_addr))

    def _parse_email(self, email_string):
        '''
        Extracts the relevant items from the email.
        '''

        self._email = email.message_from_string(email_string)

        self.requested_addr = decode_header(self._email['To'])
        if not self.requested_addr:
            syslog.syslog(syslog.LOG_INFO, 'fail: no requested address')
            return False
        
        # The 'To' field generally looks like this: 
        #    "get+fa" <get+fa@psiphon3.com>
        # So we need to strip it down to the useful part.

        self.requested_addr = strip_email(self.requested_addr)
        if not self.requested_addr:
            # Bad address. Fail.
            syslog.syslog(syslog.LOG_INFO, 'fail: unparsable requested address')
            return False

        # Convert to lowercase, since that's what's in the _conf and we want to 
        # do a case-insensitive check.
        self.requested_addr = self.requested_addr.lower()

        self._requester_addr = decode_header(self._email['Return-Path'])
        if not self._requester_addr:
            syslog.syslog(syslog.LOG_INFO, 'fail: no requester address')
            return False

        self._subject = decode_header(self._email['Subject'])
        if not self._subject: self._subject = '' 

        # Add 'Re:' to the subject
        self._subject = u'Re: %s' % self._subject

        return True
    
    def _check_verification_email(self):
        '''
        Check if the incoming email is an Amazon SES verification email that
        we should write to file so that we use the link in it.
        '''
        if settings.VERIFY_EMAIL_ADDRESS \
           and settings.VERIFY_EMAIL_ADDRESS == self.requested_addr:
            
            # Write the email to disk so that we can get the verification link 
            # out of it.
            f = open(settings.VERIFY_FILENAME, 'w')
            f.write(self._email.as_string())
            f.close()
            
            syslog.syslog(syslog.LOG_INFO, 'info: verification email received to: %s' % self.requested_addr)
            
            return True
        
        return False
        

def strip_email(email_address):
    '''
    Strips something that looks like:
        Fname Lname <mail@example.com>
    Down to just mail@example.com and returns it. If passed a plain email address, 
    will return that email. Returns False if bad email address.
    '''

    # This regex is adapted from:
    # https://gitweb.torproject.org/gettor.git/blob/HEAD:/lib/gettor/requests.py
    to_regex = '.*?(<)?([a-zA-Z0-9\+\.\-]+@[a-zA-Z0-9\+\.\-]+\.[a-zA-Z0-9\+\.\-]+)(?(1)>).*'
    match = re.match(to_regex, email_address)
    if match and match.group(2):
        return match.group(2)
    return False
    

def decode_header(header_val):
    '''
    Returns False if decoding fails. Otherwise returns the decoded value.
    '''
    try:
        hdr = email.header.decode_header(header_val)
        if not hdr: return False
        text, encoding = hdr[0]
        if not encoding: return text
        return text.decode(encoding)        
    except Exception:
        return False


def get_s3_attachment(bucketname):
    '''
    Returns a file-type object for the Psiphon 3 executable in the requested 
    bucket.
    This function checks if the file has already been downloaded. If it has, 
    it checks that the checksum still matches the file in S3. If the file doesn't
    exist, or if it the checksum doesn't match, the 
    '''
    
    # Make the attachment cache dir, if it doesn't exist 
    if not os.path.isdir(settings.ATTACHMENT_CACHE_DIR):
        os.mkdir(settings.ATTACHMENT_CACHE_DIR)
    
    # Make the connection using the credentials in the boto config file.
    conn = S3Connection()
    
    bucket = conn.get_bucket(bucketname)
    key = bucket.get_key(settings.S3_EXE_NAME)
    etag = key.etag.strip('"').lower()
    
    # We store the cached file with the bucket name as the filename
    cache_path = os.path.join(settings.ATTACHMENT_CACHE_DIR, bucketname)
    
    # Check if the file exists. If so, check if it's stale.
    if os.path.isfile(cache_path):
        cache_file = open(cache_path, 'r')
        cache_hex = hashlib.md5(cache_file.read()).hexdigest().lower()
        
        # Do the hashes match?
        if etag == cache_hex:
            cache_file.seek(0)
            return cache_file
        
        cache_file.close()
        
    # The cached file either doesn't exist or is stale.
    cache_file = open(cache_path, 'w')
    key.get_file(cache_file)
    
    # Close the file and re-open for read-only
    cache_file.close()
    cache_file = open(cache_path, 'r')
    
    return cache_file


if __name__ == '__main__':
    '''
    Note that we always exit with 0 so that the email server doesn't complain.
    '''
    
    starttime = time.clock()

    try:
        email_string = sys.stdin.read()

        if not email_string:
            syslog.syslog(syslog.LOG_CRIT, 'error: no stdin')
            exit(0)

        responder = MailResponder()

        if not responder.read_conf(settings.CONFIG_FILEPATH):
            exit(0)

        if not responder.process_email(email_string):
            exit(0)

    except Exception as e:
        syslog.syslog(syslog.LOG_CRIT, 'exception: %s: %s' % (e, traceback.format_exc()))
        
        # Should we write this exception-causing email to disk?
        if settings.EXCEPTION_DIR and email_string:
            temp = tempfile.mkstemp(suffix='.txt', dir=settings.EXCEPTION_DIR)
            tempfile = os.fdopen(temp[0], 'w')
            tempfile.write('Exception caught: %s\n' % e)
            tempfile.write('%s\n\n' % traceback.format_exc())
            tempfile.write(email_string)
            tempfile.close()
    else:
        syslog.syslog(syslog.LOG_INFO, 
                      'success: %s: %fs' % (responder.requested_addr, time.clock()-starttime))
    
    exit(0)
