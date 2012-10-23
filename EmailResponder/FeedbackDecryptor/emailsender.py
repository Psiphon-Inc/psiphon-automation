import smtplib
from email.message import Message as EmailMessage


def send(server, port, username, password,
         fromaddr, toaddrs, subject, body, replyid):
    '''
    Send email via SMTP.
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
