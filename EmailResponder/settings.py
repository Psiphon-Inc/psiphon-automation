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
Settings for how the email auto-responder operates.
'''


!!!
DELETE THESE LINEs WHEN YOU CHANGE THE VALUES IN THIS FILE FOR YOUR INSTALLATION.
Modify lines that mention "example" with values appropriate for your installation.
For Psiphon this means mostly replacing with "psiphon", "psiphon3", and "Psiphon".
!!!


import os


#
# Database connection stuff
#

DB_DBNAME = 'example'
DB_USERNAME = 'example'
DB_PASSWORD = 'example'

DB_ROOT_USERNAME = 'root'
DB_ROOT_PASSWORD = ''

#
# General processing/sending stuff
#

MAIL_RESPONDER_USERNAME = 'mail_responder'

# The location of the responder config in S3.
CONFIG_S3_BUCKET = 'psiphon-automation'
CONFIG_S3_KEY = 'EmailResponder/conf.json'

# The directory where attachment files are cached.
ATTACHMENT_CACHE_DIR = os.path.expanduser('~%s/attach_cache' % MAIL_RESPONDER_USERNAME)

# We're going to use a fixed address to reply to all email from.
# If this becomes a problem in the future, it can be changed.
RESPONSE_FROM_ADDR = 'Example Responder <noreply@example.com>'

# This address will be used as the Return-Path of sent messages. This address
# will typically receive complaints from senders and other mailservers.
COMPLAINTS_ADDRESS = 'complaints@example.com'

# These addresses will receive forwarded complaints emails and other administriva.
# Set to empty array if no such emails should be sent.
ADMIN_FORWARD_ADDRESSES = ['mick@example.com', 'keith@example.com']

# Will appear at the start of subject of administrative email sent by this server
ADMIN_FORWARD_SUBJECT_TAG = '[MailResponder]'


# This must match the local send service specified in /etc/postfix/master.cf
LOCAL_SMTP_SEND_PORT = 2525


#
# Blacklist stuff
#

BLACKLIST_DAILY_LIMIT = 3

# Email addresses from domains in this list will never be blacklisted.
# Leave empty if functionality is not desired.
BLACKLIST_EXEMPTION_DOMAINS = ['example.com']

# Email addresses from domains in this list will always be blacklisted.
# Leave empty if functionality is not desired.
BLACKLISTED_DOMAINS = ['googlegroups.com', 'getresponse.com', 'linkedin.com']


#
# Stats stuff
#

# Will appear at the start of stats email subject
STATS_SUBJECT_TAG = ADMIN_FORWARD_SUBJECT_TAG

# The address to which the stats email should be sent.
STATS_RECIPIENT_ADDRESS = 'mail@example.com'
# The address from which the stats email should be sent.
STATS_SENDER_ADDRESS_BARE = 'noreply@example.com'
STATS_SENDER_ADDRESS = 'Example Responder <%s>' % STATS_SENDER_ADDRESS_BARE

# The location of our log file
LOG_FILENAME = '/var/log/mail_responder.log'

# TODO: Use aws_helpers._get_autoscaling_group() instead of this hardcoded value
CLOUDWATCH_DIMENSIONS = { 'AutoScalingGroupName': 'mailresponder-autoscaling-group-1' }
CLOUDWATCH_NAMESPACE = 'Psiphon/MailResponder'
CLOUDWATCH_TOTAL_SENT_METRIC_NAME = 'response_sent'
CLOUDWATCH_PROCESSING_TIME_METRIC_NAME = 'processing_time'


#
# DKIM email signing stuff
#
DKIM_DOMAIN = STATS_SENDER_ADDRESS_BARE[STATS_SENDER_ADDRESS_BARE.index('@') + 1:]
DKIM_SELECTOR = 'key1'
DKIM_PRIVATE_KEY = os.path.expanduser('~%s/dkim.key' % MAIL_RESPONDER_USERNAME)


#
# Miscellaneous
#

# When exceptions occur, we may want to see the email that caused the exception.
# If the following value is not None, an email that triggers an exception will
# be written raw to a files in this directory.
# Note: This should be used only when necessary. Recording user information is
# undesireable.
EXCEPTION_DIR = os.path.expanduser('~%s/exceptions' % MAIL_RESPONDER_USERNAME)

# User that will receive email sent to incorrect addresses -- should just be a blackhole
SYSTEM_DEVNULL_USER = 'nobody'
