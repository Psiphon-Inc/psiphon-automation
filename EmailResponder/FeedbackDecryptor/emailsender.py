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


import smtplib
from email.message import Message as EmailMessage


def send(server, port, username, password,
         fromaddr, toaddrs, subject, body, replyid):
    '''
    Send email via SMTP. Throws exception on error.
    '''

    if type(toaddrs) == str:
        toaddrs = [toaddrs]

    msg = EmailMessage()

    msg.set_payload(body)
    msg['Subject'] = subject
    msg['From'] = fromaddr
    msg['To'] = toaddrs
    msg['In-Reply-To'] = replyid

    mailserver = smtplib.SMTP_SSL(server, port)
    mailserver.login(username, password)

    mailserver.sendmail(fromaddr, toaddrs, msg.as_string())
