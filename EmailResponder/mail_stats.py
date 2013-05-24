# -*- coding: utf-8 -*-

# Copyright (c) 2012, Psiphon Inc.
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
Intended to be run as a cron job to send autoresponder stats to desired email
address.

The MailStats class can be used to record stats about the mail responder.
'''

import json
import re
import os
import subprocess
import shlex
import textwrap
from boto.ses.connection import SESConnection

import settings
import sendmail
import log_processor


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


def get_send_info():

    # The number of outgoing mail queued but not sent in the previous day
    res = log_processor.dbengine.execute('SELECT COUNT(*) FROM outgoing_mail WHERE sent IS NULL AND created > UNIX_TIMESTAMP(NOW() - INTERVAL 1 DAY)*1000;')
    unsent_day = res.fetchone()[0]

    # The number of messages that expired in the past day
    res = log_processor.dbengine.execute('SELECT COUNT(*) FROM outgoing_mail WHERE expired > UNIX_TIMESTAMP(NOW() - INTERVAL 1 DAY)*1000;')
    expireds = res.fetchone()[0]

    #
    # Calculating medians is a bit of a hassle.
    #

    # Drop any existing temp tables
    res = log_processor.dbengine.execute('DROP TABLE IF EXISTS sendtime;')
    res = log_processor.dbengine.execute('DROP TABLE IF EXISTS proctime;')

    # Create a temporary table
    res = log_processor.dbengine.execute('CREATE TABLE sendtime SELECT (sent-created) AS time FROM outgoing_mail WHERE sent IS NOT NULL AND sent > UNIX_TIMESTAMP(NOW() - INTERVAL 1 DAY)*1000;')
    res = log_processor.dbengine.execute('CREATE TABLE proctime SELECT (processing_end - processing_start) AS time FROM incoming_mail WHERE created > UNIX_TIMESTAMP(NOW() - INTERVAL 1 DAY)*1000;')

    # Get the counts so we can determine the middle
    res = log_processor.dbengine.execute('SELECT COUNT(*) FROM sendtime;')
    sendtime_count = res.fetchone()[0]
    res = log_processor.dbengine.execute('SELECT COUNT(*) FROM proctime;')
    proctime_count = res.fetchone()[0]

    # Get the middle value
    res = log_processor.dbengine.execute('SELECT * FROM sendtime ORDER BY time ASC LIMIT %d, 1;' % ((sendtime_count + 1) / 2))
    median_sendtime = res.fetchone()[0]
    res = log_processor.dbengine.execute('SELECT * FROM proctime ORDER BY time ASC LIMIT %d, 1;' % ((proctime_count + 1) / 2))
    median_proctime = res.fetchone()[0]

    # Drop the tempoary tables (probably not necessary, but...)
    res = log_processor.dbengine.execute('DROP TABLE sendtime;')
    res = log_processor.dbengine.execute('DROP TABLE proctime;')

    return textwrap.dedent(
               u'''
               In the past day:
                 Median send time: %(median_sendtime)ds
                 Median process time: %(median_proctime)dms
                 Unsent: %(unsent_day)d
                 Expired: %(expireds)d
               ''' % {'unsent_day': unsent_day,
                      'median_sendtime': median_sendtime / 1000,
                      'median_proctime': median_proctime,
                      'expireds': expireds
                      })


def process_log_file(logfile):
    '''
    Takes a file-like object, processes it, extracts info about activity, and
    returns a human-readable text summary of its contents.
    '''

    logtypes = {
                'success': {
                            'regex': re.compile('^([^ ]+) .* mail_process.py: success: (.*):'),
                            'results': {}
                            },
                'fail': {
                            'regex': re.compile('^([^ ]+) .* mail_process.py: fail: (.*)'),
                            'results': {}
                            },
                'exception': {
                              'regex': re.compile('^([^ ]+) .* mail_process.py: exception: (.*)'),
                              'results': {}
                              },
                'error': {
                          'regex': re.compile('^([^ ]+) .* mail_process.py: error: (.*)'),
                          'results': {}
                          },
                }

    unmatched_lines = []

    start_timestamp = None
    end_timestamp = None

    while True:
        line = logfile.readline()
        if not line:
            break
        line = line.strip()

        match = False
        for logtype in logtypes.values():
            res = logtype['regex'].search(line)
            if not res:
                continue

            timestamp = res.groups()[0]
            val = res.groups()[1]
            logtype['results'][val] = logtype['results'].get(val, 0) + 1

            # Record the timestamp of the first and last logs.
            # Assume we're processing logs in increasing chronological order.
            if not start_timestamp:
                start_timestamp = timestamp
            end_timestamp = timestamp

            match = True
            break

        if not match:
            unmatched_lines.append(line)

    text = ''

    # Success logs

    results = logtypes['success']['results']

    text += '\nSuccessfully sent\n----------------------\n'

    text += 'TOTAL: %d\n' % sum(results.values())

    # Only itemize the entries with a reasonably large count
    for item in filter(lambda (k,v): v >= 10,
                       sorted(results.iteritems(),
                              key=lambda (k,v): (v,k),
                              reverse=True)):
        text += '%s %s\n' % (str(item[1]).rjust(4), item[0])

    # Fail logs

    results = logtypes['fail']['results']

    text += '\n\nFailures\n----------------------\n\n'

    text += 'TOTAL: %d\n' % sum(results.values())

    # Only itemize the entries with a reasonably large count
    for item in filter(lambda (k,v): v >= 10,
                       sorted(results.iteritems(),
                              key=lambda (k,v): (v,k),
                              reverse=True)):
        text += '%s %s\n' % (str(item[1]).rjust(4), item[0])

    # Process the rest of the log types

    for logtype_name in ('exception', 'error'):
        text += '\n%s\n----------------------\n\n' % logtype_name
        for info, count in logtypes[logtype_name]['results'].iteritems():
            text += '%s\nCOUNT: %d\n\n' % (info, count)

    text += '\n\nunmatched lines\n---------------------------\n'
    text += '\n'.join(unmatched_lines)

    text += '\n\nStart: %s\n  End: %s\n\n' % (start_timestamp, end_timestamp)

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
        logfile = open('%s.1' % settings.LOG_FILENAME, 'r')
        loginfo = process_log_file(logfile)
        logfile.close()
    except:
        pass

    queue_check = subprocess.Popen(shlex.split('sudo perl %s' % os.path.expanduser('~%s/postfix_queue_check.pl' % settings.MAIL_RESPONDER_USERNAME)), stdout=subprocess.PIPE).communicate()[0]
    logwatch_basic = subprocess.Popen(shlex.split('logwatch --output stdout --format text'), stdout=subprocess.PIPE).communicate()[0]

    email_body = '<pre>'

    email_body += loginfo
    email_body += '\n\n\n'
    email_body += 'Postfix queue counts\n----------------------\n' + queue_check
    email_body += '\n\n\n'
    email_body += get_send_info()
    email_body += '\n\n\n'
    email_body += get_exception_info()
    email_body += '\n\n\n'
    email_body += 'SES quota info\n----------------------\n' + get_ses_quota()
    email_body += '\n\n\n'
    email_body += 'Logwatch Basic\n----------------------\n' + logwatch_basic

    email_body += '</pre>'

    subject = '[MailResponder] Stats'

    raw_email = sendmail.create_raw_email(settings.STATS_RECIPIENT_ADDRESS,
                                          settings.STATS_SENDER_ADDRESS,
                                          subject,
                                          [['plain', email_body], ['html', email_body]])

    if not raw_email:
        exit(1)

    if not sendmail.send_raw_email_smtp(raw_email,
                                        settings.STATS_SENDER_ADDRESS,
                                        settings.STATS_RECIPIENT_ADDRESS):
        exit(1)

    exit(0)
