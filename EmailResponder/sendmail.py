# -*- coding: utf-8 -*-

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

from cStringIO import StringIO
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.header import Header
from email import Charset
from email.generator import Generator
import smtplib
from boto.ses.connection import SESConnection


# Adapted from http://radix.twistedmatrix.com/2010/07/how-to-send-good-unicode-email-with.html
def create_raw_email(recipient, from_address, subject, body):
    '''
    Creates a i18n-compatible raw email.
    body may be an array of MIME parts in the form:
        [['plain', plainbody], ['html', htmlbody], ...]
    May raise exceptions, such as if character encodings fail.
    '''

    # We expect body to be an array of mime parts. So make one if that's not 
    # what we got.
    if isinstance(body, str) or isinstance(body, unicode): 
        body = [['plain', body],]
    if body is None: body = []

    # Override python's weird assumption that utf-8 text should be encoded with
    # base64, and instead use quoted-printable (for both subject and body).  I
    # can't figure out a way to specify QP (quoted-printable) instead of base64 in
    # a way that doesn't modify global state. :-(
    Charset.add_charset('utf-8', Charset.QP, Charset.QP, 'utf-8')

    # This example is of an email with text and html alternatives.
    multipart = MIMEMultipart('alternative')

    # We need to use Header objects here instead of just assigning the strings in
    # order to get our headers properly encoded (with QP).
    # You may want to avoid this if your headers are already ASCII, just so people
    # can read the raw message without getting a headache.

    #TODO: encoding the email addresses in UTF-8 does not work with AmazonSES for now.
    #multipart['To'] = Header(recipient.encode('utf-8'), 'UTF-8').encode()
    #multipart['From'] = Header(from_address.encode('utf-8'), 'UTF-8').encode()

    multipart['To'] = Header(recipient.encode('utf-8'), 'ascii').encode()
    multipart['From'] = Header(from_address.encode('utf-8'), 'ascii').encode()

    multipart['Subject'] = Header(subject.encode('utf-8'), 'UTF-8').encode()
    
    # Attach the parts with the given encodings.

    for mimetype, content in body:
        msgpart = MIMEText(content.encode('utf-8'), mimetype, 'UTF-8')
        multipart.attach(msgpart)

    # And here we have to instantiate a Generator object to convert the multipart
    # object to a string (can't use multipart.as_string, because that escapes
    # "From" lines).

    io = StringIO()
    g = Generator(io, False) # second argument means "should I mangle From?"
    g.flatten(multipart)

    return io.getvalue()


def send_raw_email_smtp(raw_email, 
                        from_address, 
                        recipient, 
                        smtp_server='localhost'):
    '''
    Sends the raw email via the specified SMTP server.
    Returns True on success (raises exception otherwise).
    '''

    s = smtplib.SMTP(smtp_server)
    s.sendmail(from_address, recipient, raw_email)
    s.quit()

    return True

def send_raw_email_amazonses(raw_email, 
                             from_address, 
                             recipient=None,
                             aws_key=None,
                             aws_secret_key=None):
    '''
    Send the raw email via Amazon SES.
    If the credential arguments are None, boto will attempt to retrieve the
    values from environment variables and config files.
    recipient seems to be redudant with the values in the raw email headers.
    '''

    conn = SESConnection(aws_key, aws_secret_key) 

    if isinstance(recipient, str) or isinstance(recipient, unicode): 
        recipient = [recipient]

    conn.send_raw_email(raw_email, source=from_address, destinations=recipient)

    return True

    