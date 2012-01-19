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
import re
import os
import subprocess
import shlex
from boto.ses.connection import SESConnection

import settings
import sendmail


def get_ses_quota():
    '''
    Returns the simple Amazon SES quota info, in text. 
    '''
    # Open the connection. Uses creds from boto conf or env vars.
    conn = SESConnection()

    quota = conn.get_send_quota()
    
    # Getting an error when we try to call this. See:
    # http://code.google.com/p/boto/issues/detail?id=518
    #conn.close()

    return json.dumps(quota, indent=2)

def process_log_file(logfile):
    '''
    Takes a file-like object, processes it, extracts info about activity, and 
    returns a human-readable text summary of its contents.
    '''
    
    logtypes = {
                'success': {
                            'regex': re.compile('mail_process.py: success: (.*):'),
                            'results': {}
                            },
                'fail': {
                            'regex': re.compile('mail_process.py: fail: (.*)'),
                            'results': {}
                            },
                'exception': {
                              'regex': re.compile('mail_process.py: exception: (.*)'),
                              'results': {}
                              },
                'error': {
                          'regex': re.compile('mail_process.py: error: (.*)'),
                          'results': {}
                          },
                }
    logtype_order = ('success', 'fail', 'exception', 'error')
    
    unmatched_lines = []
    
    while True:
        line = logfile.readline()
        if not line: break
        line = line.strip()
        
        match = False
        for logtype in logtypes.values():
            res = logtype['regex'].search(line)
            if not res: continue
            
            val = res.groups()[0]
            logtype['results'][val] = logtype['results'][val]+1 if logtype['results'].has_key(val) else 1
            
            match = True
            break
        
        if not match:
            unmatched_lines.append(line)

    text = ''
    for logtype_name in logtype_order:
        text += '\n%s\n----------------------\n\n' % logtype_name
        for info, count in logtypes[logtype_name]['results'].iteritems():
            text += '%s\nCOUNT: %d\n\n' % (info, count)
        
    text += '\n\nunmatched lines\n---------------------------\n'
    text += '\n'.join(unmatched_lines)
    
    return text


def get_exception_info():
    if os.path.isdir(settings.EXCEPTION_DIR):
        return 'Exception files count: %d' % len(os.listdir(settings.EXCEPTION_DIR))
    else:
        return 'Exception files count: (not gathering)'


if __name__ == '__main__':

    # We want to process the most recently rotated file (so that we're processing
    # a whole day of results, and not a partial day).
    loginfo = ''
    try:
        logfile = open('%s.1'%settings.LOG_FILENAME, 'r')
        loginfo = process_log_file(logfile)
        logfile.close()
    except:
        pass

    queue_check = subprocess.Popen(shlex.split('sudo perl %s' % os.path.expanduser('~%s/postfix_queue_check.pl' % settings.MAIL_RESPONDER_USERNAME)), stdout=subprocess.PIPE).communicate()[0]
    logwatch_basic = subprocess.Popen(shlex.split('logwatch --output stdout --format text'), stdout=subprocess.PIPE).communicate()[0]
    logwatch_postfix = subprocess.Popen(shlex.split('logwatch --service postfix --range yesterday --detail 12 --output stdout --format text'), stdout=subprocess.PIPE).communicate()[0]


    email_body = '<pre>'
    
    email_body += loginfo
    email_body += '\n\n\n'
    email_body += get_exception_info()
    email_body += '\n\n\n'
    email_body += 'SES quota info\n----------------------\n' + get_ses_quota()
    email_body += '\n\n\n'
    email_body += 'Postfix queue counts\n----------------------\n' + queue_check
    email_body += '\n\n\n'
    email_body += 'Logwatch Basic\n----------------------\n' + logwatch_basic
    email_body += '\n\n\n'
    email_body += 'Logwatch Postfix\n----------------------\n' + logwatch_postfix

    email_body += '</pre>'

    subject = '[MailResponder] Stats'

    raw_email = sendmail.create_raw_email(settings.STATS_RECIPIENT_ADDRESS, 
                                          settings.STATS_SENDER_ADDRESS, 
                                          subject, 
                                          [['plain', email_body], ['html', email_body]])

    if not raw_email:
        exit(1)

    if not sendmail.send_raw_email_amazonses(raw_email, settings.STATS_SENDER_ADDRESS):
        exit(1)

    exit(0)

