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
Settings for how the email auto-responder operates.
'''

import os


#
# Database connection stuff
#

DB_DBNAME = 'psiphon'
DB_USERNAME = 'psiphon'
DB_PASSWORD = 'psiphon'

DB_ROOT_USERNAME = 'root'
DB_ROOT_PASSWORD = ''

#
# General processing/sending stuff
# 

MAIL_RESPONDER_USERNAME = 'mail_responder'

# The location of the config files.
CONFIG_DIR =  '/mail_responder_config'
CONFIG_FILEPATH = os.path.join(CONFIG_DIR, 'conf.json')

# The directory where attachment files are cached.
ATTACHMENT_CACHE_DIR = os.path.expanduser('~%s/attach_cache' % MAIL_RESPONDER_USERNAME)

# We're going to use a fixed address to reply to all email from. 
# The reasons for this are:
#   - Amazon SES requires you to register ever email address you send from;
#   - Amazon SES has a limit of 100 registered addresses;
#   - We tend to set up and down autoresponse addresses quickly.
# If this becomes a problem in the future, we could set up some kind of 
# auto-verification mechanism.
RESPONSE_FROM_ADDR = 'Psiphon Responder <noreply@psiphon3.com>'


#
# Attachment stuff
#

# The name of the Psiphon 3 executable in the S3 buckets.
S3_EXE_NAME = 'psiphon3.exe'

# The name of the attachment that's displayed in the email must be a filetype
# that Amazon SES accepts as a MIME type. But we also want it to be a filetype
# that doesn't usually have a file association (since we don't want anyone
# accidentally double-clicking and trying to open it).
ATTACHMENT_NAME = 'psiphon3.asc'


#
# Blacklist stuff
#

BLACKLIST_DAILY_LIMIT = 3


#
# Stats stuff
#

# The address to which the stats email should be sent.
STATS_RECIPIENT_ADDRESS = 'mail@example.com'
# The address from which the stats email should be sent.
STATS_SENDER_ADDRESS_BARE = 'noreply@psiphon3.com'
STATS_SENDER_ADDRESS = 'Psiphon Responder <%s>' % STATS_SENDER_ADDRESS_BARE

# The location of our log file
LOG_FILENAME = '/var/log/mail_responder.log'


#
# SES email verification stuff
# 

# In order to send an email from a particular address, Amazon SES requires that
# we verify ownership of that address. But our mail server throws away all 
# incoming email (even if it gets replied to), so there's no chance to see if
# it's from Amazon with a link we want to click. So we'll add the ability to
# specify an email address that we're expecting to receive a verification email
# to. Note that this is intended to be used for very short time periods -- only
# until the email is verified. So it should almost always be None.
VERIFY_EMAIL_ADDRESS = None
VERIFY_FILENAME = os.path.expanduser('~%s/verify.txt' % MAIL_RESPONDER_USERNAME)


#
# DKIM email signing stuff
# 
DKIM_DOMAIN = STATS_SENDER_ADDRESS_BARE[STATS_SENDER_ADDRESS_BARE.index('@')+1:]
DKIM_SELECTOR = 'key1'
DKIM_PRIVATE_KEY = os.path.join(CONFIG_DIR, 'dkim.key')

#
# Miscellaneous
#

# When exceptions occur, we may want to see the email that caused the exception.
# If the following value is not None, an email that triggers an exception will
# be written raw to a files in this directory. 
# Note: This should be used only when necessary. Recording user information is
# undesireable.
EXCEPTION_DIR = os.path.expanduser('~%s/exceptions' % MAIL_RESPONDER_USERNAME)

