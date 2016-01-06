# -*- coding: utf-8 -*-

# Copyright (c) 2014, Psiphon Inc.
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
import sys
import subprocess
import shlex
import textwrap
import datetime
import httplib
from boto.ses.connection import SESConnection
from boto.ec2.cloudwatch import CloudWatchConnection

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
    res = res.fetchone()
    median_sendtime = res[0] if res else None

    res = log_processor.dbengine.execute('SELECT * FROM proctime ORDER BY time ASC LIMIT %d, 1;' % ((proctime_count + 1) / 2))
    res = res.fetchone()
    median_proctime = res[0] if res else None

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
               ''' % {'unsent_day': unsent_day if unsent_day else 0,
                      'median_sendtime': (median_sendtime / 1000) if median_sendtime else -1,
                      'median_proctime': median_proctime if median_proctime else -1,
                      'expireds': expireds if expireds else 0
                      })


def process_log_file(logfile):
    '''
    Takes a file-like object, processes it, extracts info about activity, and
    returns a human-readable text summary of its contents.
    '''

    logtypes = {
                'success': {
                            'regex': re.compile('^([^ ]+) .* mail_process\.py.*: success: (.*):'),
                            'results': {}
                            },
                'fail': {
                            'regex': re.compile('^([^ ]+) .* mail_process\.py.*: fail: (.*)'),
                            'results': {}
                            },
                'exception': {
                              'regex': re.compile('^([^ ]+) .* mail_process\.py.*: exception: (.*)'),
                              'results': {}
                              },
                'error': {
                          'regex': re.compile('^([^ ]+) .* mail_process\.py.*: error: (.*)'),
                          'results': {}
                          },
                'bad_address': {
                          'regex': re.compile('^([^ ]+) .* log_processor\.py.*: bad_address: (.*)'),
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

    text += 'Successfully sent\n----------------------\n'

    text += 'TOTAL: %d\n' % sum(results.values())

    for item in filter(lambda (k,v): v >= 1,
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

    # Bad addresses

    results = logtypes['bad_address']['results']

    text += '\n\nBad Addresses\n----------------------\n\n'

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

    text += '\n\nStart: %s\n' % start_timestamp
    text += '  End: %s\n' % end_timestamp
    text += ' Sent: %s+00:00\n' % datetime.datetime.utcnow().isoformat()

    return text


def get_exception_info():
    if os.path.isdir(settings.EXCEPTION_DIR):
        return 'Exception files count: %d' % len(os.listdir(settings.EXCEPTION_DIR))
    else:
        return 'Exception files count: (not gathering)'


def get_instance_info():
    httpconn = httplib.HTTPConnection('169.254.169.254')
    httpconn.request('GET', '/latest/meta-data/instance-id')
    instance_id = httpconn.getresponse().read()
    httpconn.request('GET', '/latest/meta-data/instance-type')
    instance_type = httpconn.getresponse().read()
    httpconn.request('GET', '/latest/meta-data/ami-id')
    ami_id = httpconn.getresponse().read()
    return textwrap.dedent(
               u'''
                 Instance ID:   %(instance_id)s
                 Instance Type: %(instance_type)s
                 AMI ID:        %(ami_id)s
               ''' % {'instance_id': instance_id,
                      'instance_type': instance_type,
                      'ami_id': ami_id,
                      })


TOP_THRESHOLD_COUNT = 1
START_DELTA_AGO = datetime.timedelta(1)


def get_cloudwatch_top_metrics():
    conn = CloudWatchConnection()

    metrics_names = []
    next_token = None
    while True:
        res = conn.list_metrics(next_token=next_token,
                                dimensions=settings.CLOUDWATCH_DIMENSIONS,
                                namespace=settings.CLOUDWATCH_NAMESPACE)
        metrics_names.extend([m.name for m in res])
        next_token = res.next_token
        if next_token is None:
            break

    # List of tuples like [(metric_name, count), ...]
    metrics = []

    for metric_name in metrics_names:
        res = conn.get_metric_statistics(int(START_DELTA_AGO.total_seconds()),
                                         datetime.datetime.now() - START_DELTA_AGO,
                                         datetime.datetime.now(),
                                         metric_name,
                                         settings.CLOUDWATCH_NAMESPACE,
                                         'Sum',
                                         settings.CLOUDWATCH_DIMENSIONS,
                                         'Count')

        if not res:
            # Some metrics will not have (or no longer have) results
            continue

        count = int(res[0]['Sum'])

        if count >= TOP_THRESHOLD_COUNT:
            metrics.append((metric_name, count))

    metrics.sort(key=lambda x: x[1], reverse=True)

    text = 'Responses sent\n----------------------\n'
    for metric in metrics:
        metric_name = 'TOTAL' if metric[0] == settings.CLOUDWATCH_TOTAL_SENT_METRIC_NAME else metric[0]
        if metric_name == settings.CLOUDWATCH_PROCESSING_TIME_METRIC_NAME:
            continue
        text += '%s %s\n' % (str(metric[1]).rjust(5), metric_name)

    return text


if __name__ == '__main__':

    cloudwatch_info = get_cloudwatch_top_metrics()

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

    email_body = '<pre>\n'

    email_body += 'Cluster-wide stats\n\n'
    email_body += cloudwatch_info

    email_body += '\n======================\n\n'

    email_body += 'Instance-specific stats'

    email_body += '\n\n'
    email_body += loginfo

    email_body += 'Postfix queue counts\n----------------------\n' + queue_check
    email_body += '\n\n'
    email_body += get_send_info()
    email_body += '\n\n'
    email_body += get_exception_info()
    email_body += '\n\n'
    email_body += 'SES quota info\n----------------------\n' + get_ses_quota()
    email_body += '\n\n'
    email_body += 'Instance info\n----------------------\n' + get_instance_info()
    email_body += '\n\n'
    email_body += 'Logwatch Basic\n----------------------\n' + logwatch_basic

    email_body += '</pre>'

    subject = '%s Stats' % (settings.STATS_SUBJECT_TAG,)

    raw_email = sendmail.create_raw_email(settings.STATS_RECIPIENT_ADDRESS,
                                          settings.STATS_SENDER_ADDRESS,
                                          subject,
                                          [['plain', email_body], ['html', email_body]])

    if not raw_email:
        sys.exit(1)

    if not sendmail.send_raw_email_smtp(raw_email,
                                        settings.STATS_SENDER_ADDRESS,
                                        settings.STATS_RECIPIENT_ADDRESS):
        sys.exit(1)

    sys.exit(0)
