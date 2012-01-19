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
import dkim
from boto.s3.connection import S3Connection
from boto.s3.key import Key
from boto.exception import S3ResponseError
from boto.exception import BotoServerError

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
            
        except Exception as ex:
            syslog.syslog(syslog.LOG_CRIT, 'error: config file read failed: %s; file: %s' % (ex, conf_filepath))
            return False

        return True

    def process_email(self, email_string):
        '''
        Processes the given email and sends a response.
        Returns True if successful, False or exception otherwise.
        '''
        
        self._email_string = email_string

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
        
        extra_headers = { 'Reply-To': self.requested_addr }
        
        if self._requester_msgid:
            extra_headers['In-Reply-To'] = self._requester_msgid
            extra_headers['References'] = self._requester_msgid

        raw_response = sendmail.create_raw_email(self._requester_addr, 
                                                 self._response_from_addr,
                                                 self._subject,
                                                 self._conf[self.requested_addr]['body'],
                                                 attachment,
                                                 extra_headers)

        if not raw_response:
            return False
        
        raw_response = self._dkim_sign_email(raw_response)

        if not sendmail.send_raw_email_amazonses(raw_response, 
                                                 self._response_from_addr):
            return False

        return True

    def _check_blacklist(self):
        '''
        Check if the current requester address has been blacklisted.
        '''
        bl = blacklist.Blacklist()
        return bl.check_and_add(self._requester_addr)

    def _parse_email(self, email_string):
        '''
        Extracts the relevant items from the email.
        '''

        self._email = email.message_from_string(email_string)

        self.requested_addr = decode_header(self._email['X-Original-To'])
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
            dump_to_exception_file('fail: unparsable requested address\n\n%s' % self._email_string)
            return False

        # Convert to lowercase, since that's what's in the _conf and we want to 
        # do a case-insensitive check.
        self.requested_addr = self.requested_addr.lower()

        # Extract and parse the sender's (requester's) address
        
        self._requester_addr = decode_header(self._email['Return-Path'])
        if not self._requester_addr:
            syslog.syslog(syslog.LOG_INFO, 'fail: no requester address')
            return False
        
        self._requester_addr = strip_email(self._requester_addr)
        if not self._requester_addr:
            # Amazon SES bounces have '<>' for Return-Path, so they end up here.
            if self._email['Return-Path'] == 'MAILER-DAEMON@email-bounces.amazonses.com':
                syslog.syslog(syslog.LOG_INFO, 'fail: bounce')
            else:
                syslog.syslog(syslog.LOG_INFO, 'fail: unparsable requester address')
                dump_to_exception_file('fail: unparsable requester address\n\n%s' % self._email_string)
                
            return False

        self._subject = decode_header(self._email['Subject'])
        if not self._subject: self._subject = '' 

        # Add 'Re:' to the subject
        self._subject = u'Re: %s' % self._subject

        self._requester_msgid = decode_header(self._email['Message-ID'])
        if not self._requester_msgid: self._requester_msgid = None 

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
    
    def _dkim_sign_email(self, raw_email):
        '''
        Signs the raw email according to DKIM standards and returns the resulting
        email (which is the original with extra signature headers). 
        '''
        
        # Disabling DKIM signing for now. It adds a significant processing 
        # overhead, and it's not clear that it adds a significant benefit.
        # If bounces increase, we'll re-enable it and see.
        return raw_email
        
        sig = dkim.sign(raw_email, settings.DKIM_SELECTOR, settings.DKIM_DOMAIN, 
                        open(settings.DKIM_PRIVATE_KEY).read())
        return sig + raw_email
    
    def send_test_email(self, recipient, from_address, subject, body, 
                        attachment=None, extra_headers=None):
        '''
        Used for debugging purposes to send an email that's approximately like
        a response email. 
        NOTE: from_address must be a sender that's verified with Amazon SES.
        '''
        raw = sendmail.create_raw_email(recipient, from_address, subject, body, 
                                        attachment, extra_headers)
        if not raw:
            print 'create_raw_email failed'
            return False
        
        raw = self._dkim_sign_email(raw)
        
        if not sendmail.send_raw_email_amazonses(raw, from_address):
            print 'send_raw_email_amazonses failed'
            return False
        
        print 'Email sent'
        return True
        

def strip_email(email_address):
    '''
    Strips something that looks like:
        Fname Lname <mail@example.com>
    Down to just mail@example.com and returns it. If passed a plain email address, 
    will return that email. Returns False if bad email address.
    '''

    # This regex is adapted from:
    # https://gitweb.torproject.org/gettor.git/blob/HEAD:/lib/gettor/requests.py
    to_regex = '.*?(<)?([a-zA-Z0-9_\+\.\-]+@[a-zA-Z0-9\+\.\-]+\.[a-zA-Z0-9\+\.\-]+)(?(1)>).*'
    match = re.match(to_regex, email_address)
    if match and match.group(2):
        return match.group(2)
    return False
    

def decode_header(header_val):
    '''
    Returns None if decoding fails. Otherwise returns the decoded value.
    '''
    try:
        if not header_val: return None
        
        hdr = email.header.decode_header(header_val)
        if not hdr: return None
        decoded = u''
        
        return ' '.join([text.decode(encoding) if encoding else text for text,encoding in hdr])
    except:
        return None


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


def dump_to_exception_file(string):
    if settings.EXCEPTION_DIR:
        temp = tempfile.mkstemp(suffix='.txt', dir=settings.EXCEPTION_DIR)
        f = os.fdopen(temp[0], 'w')
        f.write(string)
        f.close()


def process_input(email_string):
    '''
    Process the email in email_string. Returns False on error; returns the 
    requested address on success.
    '''
    
    responder = MailResponder()

    if not responder.read_conf(settings.CONFIG_FILEPATH):
        return False

    try:
        if not responder.process_email(email_string):
            return False
    except BotoServerError as ex:
        if ex.error_message == 'Address blacklisted.':
            syslog.syslog(syslog.LOG_CRIT, 'fail: requester address blacklisted by SES')
            return False
        else:
            raise
        
    return responder.requested_addr


if __name__ == '__main__':
    '''
    Note that we always exit with 0 so that the email server doesn't complain.
    '''
    
    starttime = time.time()

    try:
        email_string = sys.stdin.read()
        
        if not email_string:
            syslog.syslog(syslog.LOG_CRIT, 'error: no stdin')
            exit(0)

        requested_addr = process_input(email_string) 
        if not requested_addr:
            exit(0)

    except Exception as ex:
        syslog.syslog(syslog.LOG_CRIT, 'exception: %s: %s' % (ex, traceback.format_exc()))
        
        # Should we write this exception-causing email to disk?
        if settings.EXCEPTION_DIR and email_string:
            dump_to_exception_file('Exception caught: %s\n%s\n\n%s' % (ex, 
                                                                       traceback.format_exc(), 
                                                                       email_string))
    else:
        syslog.syslog(syslog.LOG_INFO, 
                      'success: %s: %fs' % (requested_addr, time.time()-starttime))
    
    exit(0)
