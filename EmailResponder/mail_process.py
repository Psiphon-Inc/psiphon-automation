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

import sendmail
import blacklist


# We're going to use a fixed address to reply to all email from. 
# The reasons for this are:
#   - Amazon SES requires you to register ever email address you send from;
#   - Amazon SES has a limit of 100 registered addresses;
#   - We tend to set up and down autoresponse addresses quickly.
# If this becomes a problem in the future, we could set up some kind of 
# auto-verification mechanism.
RESPONSE_FROM_ADDR = 'Psiphon Responder <noreply@psiphon3.com>'

# When exceptions occur, we may want to see the email that caused the exception.
# If the following value is not None, an email that triggers an exception will
# be written raw to a files in this directory. 
# Note: This should be used only when necessary. Recording user information is
# undesireable.
EXCEPTION_DIR = os.path.expanduser('~/exceptions')

# In order to send an email from a particular address, Amazon SES requires that
# we verify ownership of that address. But our mail server throws away all 
# incoming email (even if it gets replied to), so there's no chance to see if
# it's from Amazon with a link we want to click. So we'll add the ability to
# specify an email address that we're expecting to receive a verification email
# to. Note that this is intended to be used for very short time periods -- only
# until the email is verified. So it should almost always be None.
VERIFY_EMAIL_ADDRESS = None
VERIFY_FILENAME = os.path.expanduser('~/verify.txt')


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

            self._response_from_addr = RESPONSE_FROM_ADDR

            # Note that json.load reads in unicode strings
            self._conf = json.load(conffile)
            
        except Exception as e:
            syslog.syslog(syslog.LOG_CRIT, 'Failed to read conf file: %s' % e)
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
            syslog.syslog(syslog.LOG_INFO, 'recip_addr invalid: %s' % self.requested_addr)
            return False
        
        # Check if the user is (or should be) blacklisted
        if not self._check_blacklist():
            syslog.syslog(syslog.LOG_INFO, 'requester blacklisted')
            return False

        raw_response = sendmail.create_raw_email(self._requester_addr, 
                                                 self._response_from_addr,
                                                 self._subject,
                                                 self._conf[self.requested_addr])

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
            syslog.syslog(syslog.LOG_INFO, 'No recip_addr')
            return False
        
        # The 'To' field generally looks like this: 
        #    "get+fa" <get+fa@psiphon3.com>
        # So we need to strip it down to the useful part.

        self.requested_addr = strip_email(self.requested_addr)
        if not self.requested_addr:
            # Bad address. Fail.
            syslog.syslog(syslog.LOG_INFO, 'Unparsable requested_addr')
            return False

        # Convert to lowercase, since that's what's in the _conf and we want to 
        # do a case-insensitive check.
        self.requested_addr = self.requested_addr.lower()

        self._requester_addr = decode_header(self._email['Return-Path'])
        if not self._requester_addr:
            syslog.syslog(syslog.LOG_INFO, 'No _requester_addr')
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
        if VERIFY_EMAIL_ADDRESS and VERIFY_EMAIL_ADDRESS == self.requested_addr:
            # Write the email to disk so that we can get the verification link 
            # out of it.
            f = open(VERIFY_FILENAME, 'w')
            f.write(self._email.as_string())
            f.close()
            
            syslog.syslog(syslog.LOG_INFO, 'verification email received to: %s' % self.requested_addr)
            
            return True
        
        return False
        



if __name__ == '__main__':
    '''
    Note that we always exit with 0 so that the email server doesn't complain.
    '''
    
    starttime = time.clock()

    if len(sys.argv) < 2:
        raise Exception('Not enough arguments. conf file required')

    conf_filename = sys.argv[1]

    if not os.path.isfile(conf_filename):
        raise Exception('conf file must exist: %s' % conf_filename)

    try:
        email_string = sys.stdin.read()

        if not email_string:
            syslog.syslog(syslog.LOG_CRIT, 'No stdin')
            exit(0)

        responder = MailResponder()

        if not responder.read_conf(conf_filename):
            exit(0)

        if not responder.process_email(email_string):
            exit(0)

    except Exception as e:
        syslog.syslog(syslog.LOG_CRIT, 'Exception caught: %s' % e)
        syslog.syslog(syslog.LOG_CRIT, traceback.format_exc())
        
        # Should we write this exception-causing email to disk?
        if EXCEPTION_DIR and email_string:
            temp = tempfile.mkstemp(suffix='.txt', dir=EXCEPTION_DIR)
            tempfile = os.fdopen(temp[0], 'w')
            tempfile.write('Exception caught: %s\n' % e)
            tempfile.write('%s\n\n' % traceback.format_exc())
            tempfile.write(email_string)
            tempfile.close()
    else:
        syslog.syslog(syslog.LOG_INFO, 
                      'Responded successfully to request for: %s: %fs' % (responder.requested_addr, time.clock()-starttime))
    
    exit(0)
