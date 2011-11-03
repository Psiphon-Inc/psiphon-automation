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
'''

import json
from boto.ses.connection import SESConnection

import sendmail


RECIPIENT_ADDRESS = 'mail@example.com'
SENDER_ADDRESS = 'Psiphon Responder <noreply@psiphon3.com>'


if __name__ == '__main__':

    # Open the connection. Uses creds from boto conf or env vars.
    conn = SESConnection()

    quota = conn.get_send_quota()
    
    # Getting an error when we try to call this. See:
    # http://code.google.com/p/boto/issues/detail?id=518
    #conn.close()
    
    email_body = ''
    email_body += json.dumps(quota, indent=2)
    email_body += '\n\n'

    subject = '[MailResponder] Stats'

    raw_email = sendmail.create_raw_email(RECIPIENT_ADDRESS, 
                                          SENDER_ADDRESS, 
                                          subject, 
                                          email_body)

    if not raw_email:
        exit(1)

    if not sendmail.send_raw_email_amazonses(raw_email, SENDER_ADDRESS):
        exit(1)

    exit(0)

