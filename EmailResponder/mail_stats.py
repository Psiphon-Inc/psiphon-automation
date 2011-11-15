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
from boto.ses.connection import SESConnection

import settings
import sendmail


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
    for logtype_name in logtypes:
        text += '\n%s\n----------------------\n\n' % logtype_name
        for info, count in logtypes[logtype_name]['results'].iteritems():
            text += '%s\nCOUNT: %d\n\n' % (info, count)
        
    text += '\n\nunmatched lines\n---------------------------\n'
    text += '\n'.join(unmatched_lines)
    
    return text


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

    # Open the connection. Uses creds from boto conf or env vars.
    conn = SESConnection()

    quota = conn.get_send_quota()
    
    # Getting an error when we try to call this. See:
    # http://code.google.com/p/boto/issues/detail?id=518
    #conn.close()
    
    email_body = ''
    email_body += json.dumps(quota, indent=2)
    email_body += '\n\n\n'
    email_body += loginfo

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

