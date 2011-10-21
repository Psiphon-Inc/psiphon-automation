import sys
import os
import syslog
import email
import json
import re

import sendmail


def get_email_localpart(email_address):
    addr_regex = '([a-zA-Z0-9\+\.\-]+)@([a-zA-Z0-9\+\.\-]+)\.([a-zA-Z0-9\+\.\-]+)'
    match = re.match(addr_regex, email_address)
    if match:
        return match.group(1)

    # Bad address. 
    return False


class MailResponder:
    '''
    Takes a configuration file and an email and sends back the appropriate 
    response to the sender.
    '''

    def __init__(self):
        self._conf = None
        self._email = None

    def read_conf(self, conf_filepath):
        '''
        Reads in the given configuration file.
        Return True if successful, False otherwise.
        '''

        try:
            conffile = open(conf_filepath, 'r')

            # Note that json.load reads in unicode strings
            self._conf = json.load(conffile)

            # The keys in our conf file may be full email addresses, but we 
            # really just want them to be the address localpart (the part before the @)
            for addr in self._conf.keys():
                localpart = get_email_localpart(addr)
                if not localpart: 
                    # if a localpart can't be found properly, just leave it
                    continue
                self._conf[localpart] = self._conf.pop(addr)

        except Exception as e:
            syslog.syslog(syslog.LOG_CRIT, 'Failed to read conf file: %s' % e)
            return False

        return True

    def process_email(self, email_string):
        '''
        Processes the given email and sends a response.
        Returns True if successful, False otherwise.
        '''

        if not self._parse_email(email_string):
            return False

        if not self._conf.has_key(self._recip_localpart):
            syslog.syslog(syslog.LOG_INFO, 'recip_addr invalid: %s' % self._recip_addr)
            return False

        if not sendmail.sendmail(self._recip_addr, 
                                 self._sender_addr, 
                                 self._subject,
                                 self._conf[self._recip_localpart]):
            return False

        return True

    def _parse_email(self, email_string):
        '''
        Extracts the relevant items from the email.
        '''

        # Note that the email fields will be UTF-8, but we need them in unicode
        # before trying to send the response. Hence the .decode('utf-8') calls.

        self._email = email.message_from_string(email_string)

        # DEBUG
        #for x in self._email.keys():
        #    syslog.syslog(syslog.LOG_INFO, '%s:%s'%(x, self._email[x]))
        #exit(0)

        self._recip_addr = self._email['To'].decode('utf-8')
        if not self._recip_addr:
            syslog.syslog(syslog.LOG_INFO, 'No recip_addr')
            return False
        
        # The 'To' field generally looks like this: 
        #    "get+fa" <get+fa@psiphon3.com>
        # So we need to strip it down to the useful part.
        # This regex is adapted from:
        # https://gitweb.torproject.org/gettor.git/blob/HEAD:/lib/gettor/requests.py

        to_regex = '.*?(<)?([a-zA-Z0-9\+\.\-]+@[a-zA-Z0-9\+\.\-]+\.[a-zA-Z0-9\+\.\-]+)(?(1)>).*'
        match = re.match(to_regex, self._recip_addr)
        if match:
            self._recip_addr = match.group(2)
        else:
            # Bad address. Fail.
            syslog.syslog(syslog.LOG_INFO, 'Unparsable recip_addr')
            return False

        # We also want just the localpart of the email address (get+fa or whatever).
        self._recip_localpart = get_email_localpart(self._recip_addr)
        if not self._recip_localpart:
            # Bad address. Fail.
            syslog.syslog(syslog.LOG_INFO, 'Bad recip_addr')
            return False
        
        self._sender_addr = self._email['Return-Path'].decode('utf-8')
        if not self._sender_addr:
            syslog.syslog(syslog.LOG_INFO, 'No sender_addr')
            return False

        self._subject = self._email['Subject'].decode('utf-8')

        # Add 'Re:' to the subject
        self._subject = u'Re: %s' % self._subject

        return True



if __name__ == '__main__':
    '''
    Note that we always exit with 0 so that the email server doesn't complain.
    '''

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
    
    exit(0)
