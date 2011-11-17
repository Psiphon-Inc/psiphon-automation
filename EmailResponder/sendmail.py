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
from email.mime.base import MIMEBase
from email.header import Header
from email import Charset
from email.generator import Generator
from email import encoders
import smtplib
from boto.ses.connection import SESConnection


# Adapted from http://radix.twistedmatrix.com/2010/07/how-to-send-good-unicode-email-with.html
def create_raw_email(recipient, from_address, subject, body, attachment=None, extra_headers=None):
    '''
    Creates a i18n-compatible raw email.
    body may be an array of MIME parts in the form:
        [['plain', plainbody], ['html', htmlbody], ...]
    May raise exceptions, such as if character encodings fail.
    attachment should be a tuple of (file-type-object, display-filename).
    extra_headers should be a dictionary of header-name:header-string values.
    '''
    
    # For email with an attachment, the MIME structure will be as follows: 
    #    multipart/mixed
    #        multipart/alternative
    #            text/plain - the plain text message
    #            text/html - the html message
    #        application/octet-stream - the attachment
    #
    # For email without an attachment, it will be the same, but we'll omit the
    # last piece.

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

    # The root MIME section.
    msgRoot = MIMEMultipart('mixed')

    # We need to use Header objects here instead of just assigning the strings in
    # order to get our headers properly encoded (with QP).
    # You may want to avoid this if your headers are already ASCII, just so people
    # can read the raw message without getting a headache.

    #TODO: encoding the email addresses in UTF-8 does not work with AmazonSES for now.
    #multipart['To'] = Header(recipient.encode('utf-8'), 'UTF-8').encode()
    #multipart['From'] = Header(from_address.encode('utf-8'), 'UTF-8').encode()

    msgRoot['To'] = Header(recipient.encode('utf-8'), 'ascii').encode()
    msgRoot['From'] = Header(from_address.encode('utf-8'), 'ascii').encode()

    msgRoot['Subject'] = Header(subject.encode('utf-8'), 'UTF-8').encode()
    
    if extra_headers:
        for header_name, header_value in extra_headers.iteritems():
            # We need a special case for the Reply-To header. Like To and From,
            # it needs to be ASCII encoded.
            encoding = 'UTF-8'
            if header_name.lower() == 'reply-to': encoding = 'ascii'
            msgRoot[header_name] = Header(header_value.encode('utf-8'), encoding).encode()
    
    # The MIME section that contains the plaintext and HTML alternatives.
    msgAlternative = MIMEMultipart('alternative')
    msgRoot.attach(msgAlternative)
    
    # Attach the body alternatives with the given encodings.
    for mimetype, content in body:
        msgpart = MIMEText(content.encode('utf-8'), mimetype, 'UTF-8')
        msgAlternative.attach(msgpart)
        
    # Attach the attachment
    if attachment:
        fp, filename = attachment

        msgAttachment = MIMEBase('application', 'octet-stream')

        msgAttachment.add_header('Content-Disposition', 'attachment', filename=filename)
        
        msgAttachment.set_payload(fp.read())
        fp.close()
        
        encoders.encode_base64(msgAttachment)
        
        msgRoot.attach(msgAttachment)

    # And here we have to instantiate a Generator object to convert the multipart
    # object to a string (can't use multipart.as_string, because that escapes
    # "From" lines).

    io = StringIO()
    g = Generator(io, False) # second argument means "should I mangle From?"
    g.flatten(msgRoot)

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
    
    # Getting an error when we try to call this. See:
    # http://code.google.com/p/boto/issues/detail?id=518
    #conn.close()

    return True

    